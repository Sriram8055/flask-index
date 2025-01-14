from flask import Flask, request, jsonify
import requests
import asyncio
import openai
import os
from crawl4ai import *
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from flask_cors import cross_origin
from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
OPENAI_BASE_URL = os.getenv('OPENAI_BASE_URL', "https://api.sambanova.ai/v1")
MONGODB_URI = os.getenv('MONGODB_URI')
SERPAPI_API_KEY = os.getenv('SERPAPI_API_KEY')



explanation = ""
samba_client = openai.OpenAI(
    api_key='9bed39a3-04ca-420e-ba3b-1fcf07ed0e60', 
    base_url="https://api.sambanova.ai/v1",
)
# Initialize OpenAI client
client = MongoClient((MONGODB_URI), server_api=ServerApi('1'))
# explanation = ""
# Initialize Flask app
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "https://clarifai.vercel.app"}})

# MongoDB connection setup

db = client['Main']
collection = db['main']

# Function to store error information in MongoDB
def store_error_info(error_message, llm_explanation, results):
    document = {
        "error_message": error_message,
        "llm_explanation": llm_explanation,
        "links": results
    }
    collection.insert_one(document)

# Function to validate inputs
def validate_inputs(error_message):
    if not error_message:
        return "Error message cannot be empty."
    if len(error_message) < 5:
        return "Error message must be at least 5 characters long."  
    return None

# Function to call the Sambanova API for Q&A
def sambanova(query, ip):
    client = openai.OpenAI(
        api_key=OPENAI_API_KEY, 
        base_url=OPENAI_BASE_URL,
    )
    response = client.chat.completions.create(
                model='Meta-Llama-3.1-8B-Instruct',
                messages=[{"role": "system", "content": """
                        Please provide a detailed explanation for the following error message in a well-structured markdown format. If the content is relevant to this query {query}, then take it as a reference and include the possible causes, step-by-step solutions, and any relevant code snippets or examples.
                        Note: Don't include any HTML tags and there should be an empty line between each paragraph like error message and step-by-step solution,also dont leave tab space before the code '''bash''' and must follow the below format:
                        ### Error Message:  
                           
                        error message
                        
                        ### Step-by-Step Solution: 
                         
                        explanation
                        -
                        -

                        ### Example:  
                           
                        example
                        '''
                        '''
                           
                           """},
                        {"role": "user", "content": ip}],
                max_tokens=1000,
                temperature=0.1,
                top_p=0.1
            )
    print(response.choices[0].message.content)
    return response.choices[0].message.content




def sambanova1(query):
    client = openai.OpenAI(
        api_key=OPENAI_API_KEY, 
        base_url=OPENAI_BASE_URL,
    )

    response = client.chat.completions.create(
        model='Meta-Llama-3.1-8B-Instruct',
       messages=[{"role":"system","content":"You are a error solution giving assistant who can explain the error message in well structured markdown format "},{"role":"user","content":f"This issue is still persisting: {query}"}],
        temperature =  0.1,
        top_p = 0.1
    )
    print(response.choices[0].message.content)
    return response.choices[0].message.content
      



# Function to search for related Stack Overflow questions
def search_questions(query, tag):
    url = "https://serpapi.com/search"
    params = {
        "engine": "google",
        "q": f"{query} site:stackoverflow.com {tag}",
        "api_key": SERPAPI_API_KEY,
        "num": 10,
        "sort": "relevance",
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        return data.get('organic_results', [])
    else:
        print(f"Error: {response.status_code} - {response.text}")
        return None

# Function to extract question IDs from search results

# Function to extract question ID from Stack Overflow link

# Function to fetch top answer for a question
# Function to crawl and process web content asynchronously
async def crawl_and_process(url):
    async with AsyncWebCrawler(verbose=True) as crawler:
        config = CrawlerRunConfig(
            cache_mode=CacheMode.ENABLED,
            excluded_tags=['nav', 'footer', 'aside'],
            remove_overlay_elements=True,
            markdown_generator=DefaultMarkdownGenerator(
                content_filter=PruningContentFilter(threshold=0.48, threshold_type="fixed", min_word_threshold=0),
                options={
                    "ignore_links": True
                }
            ),
        )
        result = await crawler.arun(
            url=url,
            config=config,
        )
        return result.markdown_v2.raw_markdown

# Function to process content with SambaNova LLM
def process_with_llm(content):
    response = samba_client.chat.completions.create(
        model='Meta-Llama-3.3-70B-Instruct',
        messages=[
            {"role": "system", "content": """
                        Please provide a detailed explanation for the following error message in a well-structured markdown format. If the content is relevant to this query {query}, then take it as a reference and include the possible causes, step-by-step solutions, and any relevant code snippets or examples.
                        Note: Don't include any HTML tags and there should be an empty line between each paragraph like error message and step-by-step solution,also dont leave tab space before the code '''bash''' and must follow the below format:
                        ### Error Message:  
                           
                        error message
                        
                        ### Step-by-Step Solution: 
                         
                        explanation
                        -
                        -

                        ### Example:  
                           
                        example
                        '''
                        '''
                           
                           """},
            {"role": "user", "content": content}
        ],
        temperature=0.1,
        top_p=0.1
    )
    return response.choices[0].message.content

# Main function to crawl, process, and generate response
async def app_function(url):
    print(f"Crawling and processing content from: {url}")
    raw_markdown = await crawl_and_process(url)
    print("Web content fetched and cleaned!")

    print("\nSending content to SambaNova LLM...")
    response_text = process_with_llm(raw_markdown[:5000])  # Limit content to avoid exceeding API input limits
    print("\nResponse from SambaNova LLM:")
    print(response_text)
    return response_text

# Function to run app with URL
def run_app(url):
    return asyncio.run(app_function(url))


# Route to retrieve the history of stored error messages and their explanations
@app.route('/history', methods=['GET'])
def get_history():
    try:
        history = list(collection.find({}, {"_id": 0, "error_message": 1, "llm_explanation": 1, "links": 1}))
        return jsonify({"history": history}), 200
    except Exception as e:
        return jsonify({"error": f"Failed to fetch history: {str(e)}"}), 500

# Route to handle the initial query and fetch related Stack Overflow answers

@app.route('/', methods=['POST'])
def index():
    results = []
    answers_list = []
    data = request.get_json()
    query = data.get('query')
    tag = data.get('tag')

    # Validate the inputs
    validation_error = validate_inputs(query)
    if validation_error:
        return jsonify({"error": validation_error}), 400

    # Search for questions based on the query and tag using SERPAPI
    results = search_questions(query, tag)
    
    if not results:
        return jsonify({"error": "No results found"}), 404

    # Extract top 3 links from the search results
    top_3_links = [result['link'] for result in results[:3]]

    # Print the top 3 links
    for idx, link in enumerate(top_3_links, 1):
        print(f"Link {idx}: {link}")
        
        # Call the web crawling function for each link and process with SambaNova LLM
        response_text = run_app(link)

        # Append the response to answers_list
        answers_list.append({
            'link': link,
            'samba_response': response_text
        })

        # Store error info if any issues arise
        store_error_info(query, response_text, results)

    # Return the results with answers_list in the JSON response
    return jsonify({"results": results, "answers_list": answers_list})

# Route to handle follow-up Q&A questions
@app.route('/qa', methods=['POST'])
def qa_bot():
    """
    Endpoint for handling follow-up questions using the LLM.
    """
    try:
        data = request.get_json()
        print(data)
        user_question = data.get('query')
        print(user_question)
        print("-"*100)
        llm_response = sambanova1(query=user_question)
        # llm_response = "This is a test response for debugging."

        
        return jsonify({"response": llm_response}), 200
    except Exception as e:
        return jsonify({"error": f"Failed to process the question: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(debug=True,host="0.0.0.0", port=5001)
