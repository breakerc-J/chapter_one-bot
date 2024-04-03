from langchain.prompts import ChatPromptTemplate
from langchain.document_loaders import UnstructuredFileLoader
from langchain.embeddings import CacheBackedEmbeddings, OpenAIEmbeddings
from langchain.schema.runnable import RunnableLambda, RunnablePassthrough
from langchain.storage import LocalFileStore
from langchain.text_splitter import CharacterTextSplitter
from langchain.vectorstores.faiss import FAISS
from langchain.chat_models import ChatOpenAI
from langchain.callbacks.base import BaseCallbackHandler
from langchain.memory import ConversationSummaryBufferMemory
import streamlit as st
import os

st.set_page_config(
    page_title="DocumentGPT",
    page_icon="📃",
)

class ConversationSummaryBufferMemory:
    def __init__(self, max_length=5):
        self.max_length = max_length
        self.buffer = []

    def add(self, message):
        self.buffer.append(message)
        if len(self.buffer) > self.max_length:
            self.buffer.pop(0)
    
    def get_summary(self):
        return " ".join(self.buffer)
    
conversation_memory = ConversationSummaryBufferMemory()

def update_conversation_memory(message, role):
    conversation_memory.add(f"{role}: {message}")
    return conversation_memory.get_summary()


class ChatCallbackHandler(BaseCallbackHandler):
    message = ""

    def on_llm_start(self, *args, **kwargs):
        self.message_box = st.empty()

    def on_llm_end(self, *args, **kwargs):
        save_message(self.message, "ai")

    def on_llm_new_token(self, token, *args, **kwargs):
        self.message += token
        self.message_box.markdown(self.message)

if "messages" not in st.session_state:
    st.session_state["messages"] = []

if "api_key" not in st.session_state:
    st.session_state["api_key"] = None

if "api_key_bool" not in st.session_state:
    st.session_state["api_key_bool"] = False

pattern = r'sk-.*'

llm = ChatOpenAI(
    temperature=0.1,
    streaming=True,
    callbacks=[
        ChatCallbackHandler(),
    ],
    openai_api_key=st.session_state["api_key"],

)


@st.cache_data(show_spinner="Embedding file...")
def embed_file(file):
    file_content = file.read()
    file_path = f"./.cache/files/{file.name}"
    os.makedirs(f"./..cache/files/", exist_ok=True)
    with open(file_path, "wb") as f:
        f.write(file_content)
    os.makedirs(f"./..cache/embeddings", exist_ok=True)
    cache_dir = LocalFileStore(f"./.cache/embeddings/{file.name}")
    splitter = CharacterTextSplitter.from_tiktoken_encoder(
        separator="\n",
        chunk_size=600,
        chunk_overlap=100,
    )
    loader = UnstructuredFileLoader(file_path)
    docs = loader.load_and_split(text_splitter=splitter)
    embeddings = OpenAIEmbeddings()
    cached_embeddings = CacheBackedEmbeddings.from_bytes_store(embeddings, cache_dir)
    vectorstore = FAISS.from_documents(docs, cached_embeddings)
    retriever = vectorstore.as_retriever()
    return retriever

def save_api_key(api_key):
    st.session_state["api_key"] = api_key

def save_message(message, role):
    st.session_state["messages"].append({"message": message, "role": role})


def send_message(message, role, save=True):
    with st.chat_message(role):
        st.markdown(message)
    if save:
        save_message(message, role)


def paint_history():
    for message in st.session_state["messages"]:
        send_message(
            message["message"],
            message["role"],
            save=False,
        )


def format_docs(docs):
    return "\n\n".join(document.page_content for document in docs)


prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """
            Answer the question using ONLY the following context. If you don't know the answer just say you don't know. DON'T make anything up.
            
            Context: {context}
            """,
        ),
        ("human", "{question}"),
    ]
)


st.title("DocumentGPT")

st.markdown(
    """
Welcome!
            
Use this chatbot to ask questions to an AI about your files!

Upload your files on the sidebar.
"""
)

with st.sidebar:
    api_key = st.text_input("Please enter your OPENAI_API_KEY.").strip()

    if api_key:
        save_api_key(api_key)
        st.write("API_KEY has been entered.")
        st.session_state["api_key_bool"] = True
        st.session_state["api_key"] = api_key

    button = st.button("SAVE")

    if button:
        save_api_key(api_key)

        if api_key == "":
            st.write("Please enter OPENAI_API_KEY.")
            

with st.sidebar:
    file = st.file_uploader(
        "Upload a .txt .pdf or .docx file",
        type=["pdf", "txt", "docx"],
    )
if (st.session_state["api_key_bool"] == True) and (st.session_state["api_key"] != None):
    if file:
        retriever = embed_file(file)
        send_message("I'm ready! Ask away!", "ai", save=False)
        paint_history()
        message = st.chat_input("Ask anything about your file...")
        if message:
            send_message(message, "human")
            chain = {
                "context": retriever | RunnableLambda(format_docs) | RunnableLambda(lambda docs: update_conversation_memory(docs, "system")),
                "question": RunnablePassthrough() | RunnableLambda(lambda question: update_conversation_memory(question, "human")),
            } | prompt | llm
            with st.chat_message("ai"):
                chain.invoke(message)
                 
    else:
        st.session_state["messages"]=[]