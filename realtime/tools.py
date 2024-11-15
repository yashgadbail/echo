import asyncpg
import numpy as np
import openai  # Assumes the OpenAI library is correctly configured

# Generate embeddings using OpenAI API
async def generate_embedding(text: str) -> np.ndarray:
    # Using a model version check for compatibility
    response = openai.Embedding.create(
        model="text-embedding-ada-002",
        input=text
    )
    return np.array(response['data'][0]['embedding'])

# Define the search tool for PGVector index
async def search_pg_vector_handler(query: str):
    # Generate the embedding of the query
    query_embedding = await generate_embedding(query)

    # Ensure embedding is compatible with PGVector by converting to a list
    query_vector = query_embedding.tolist()

    # PostgreSQL DSN setup
    dsn = "postgresql://user:password@localhost:5432/mydatabase"
    
    # Perform similarity search using a context manager for the database connection
    async with asyncpg.create_pool(dsn=dsn) as pool:
        async with pool.acquire() as conn:
            sql = """
                SELECT product_id, name, description, embedding <=> $1 AS similarity
                FROM products
                ORDER BY similarity
                LIMIT 5;  -- Top 5 most similar results
            """
            
            # Execute the query and fetch results
            results = await conn.fetch(sql, query_vector)

    # Format the results for user readability
    result_text = "\n".join([
        f"Product ID: {row['product_id']}, Name: {row['name']}, Similarity: {row['similarity']:.4f}"
        for row in results
    ])
    
    return result_text

# Define the tool definition for `search_pg_vector`
search_pg_vector_def = {
    "name": "search_pg_vector",
    "description": "Search for products using a vector similarity search",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "A textual query to search for similar products"
            }
        },
        "required": ["query"]
    }
}

# Handler for the `search_pg_vector` tool, wraps the core handler
async def search_pg_vector_handler_tool(query: str):
    search_results = await search_pg_vector_handler(query)
    return f"Search results:\n{search_results}"

# Add to the tools list for integration
tools = [(search_pg_vector_def, search_pg_vector_handler_tool)]
