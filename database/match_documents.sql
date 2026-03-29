CREATE OR REPLACE FUNCTION match_documents(
  query_embedding vector(1536),
  match_count int DEFAULT 5
)
RETURNS TABLE (
  id bigint,
  content text,
  metadata jsonb,
  similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    pokemon_embeddings.id,
    pokemon_embeddings.content,
    pokemon_embeddings.metadata,
    1 - (pokemon_embeddings.embedding <=> query_embedding) AS similarity
  FROM pokemon_embeddings
  ORDER BY pokemon_embeddings.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;
