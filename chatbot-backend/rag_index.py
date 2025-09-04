import os
from langchain.vectorstores import Chroma
from langchain.embeddings import OpenAIEmbeddings
from langchain.document_loaders import DirectoryLoader, CSVLoader, TextLoader
from dotenv import load_dotenv

load_dotenv()

PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

def build_index():
    # Load Markdown or CSV files
    loader_md = DirectoryLoader("datasets", glob="*.md", loader_cls=TextLoader)
    loader_csv = DirectoryLoader("datasets", glob="*.csv", loader_cls=CSVLoader)
    
    documents = loader_md.load() + loader_csv.load()
    
    # Create embeddings
    embeddings = OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY)
    
    # Create Chroma collection
    db = Chroma.from_documents(documents, embeddings, persist_directory=PERSIST_DIR)
    db.persist()
    print(f"[+] Indexed {len(documents)} documents to Chroma at {PERSIST_DIR}")

if __name__ == "__main__":
    build_index()