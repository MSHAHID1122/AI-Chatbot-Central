from langchain.vectorstores import Chroma
from langchain.embeddings import OpenAIEmbeddings
from langchain.document_loaders import DirectoryLoader, CSVLoader, TextLoader

# Import centralized config instead of using .env directly
from config import OPENAI_API_KEY, CHROMA_PERSIST_DIR, DATA_DIR

def build_index():
    # Load Markdown and CSV files from datasets directory inside DATA_DIR
    loader_md = DirectoryLoader(str(DATA_DIR), glob="*.md", loader_cls=TextLoader)
    loader_csv = DirectoryLoader(str(DATA_DIR), glob="*.csv", loader_cls=CSVLoader)
    
    documents = loader_md.load() + loader_csv.load()
    
    if not documents:
        print("[!] No documents found in datasets.")
        return
    
    # Create embeddings
    embeddings = OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY)
    
    # Create Chroma collection
    db = Chroma.from_documents(documents, embeddings, persist_directory=str(CHROMA_PERSIST_DIR))
    db.persist()
    print(f"[+] Indexed {len(documents)} documents to Chroma at {CHROMA_PERSIST_DIR}")

if __name__ == "__main__":
    build_index()
