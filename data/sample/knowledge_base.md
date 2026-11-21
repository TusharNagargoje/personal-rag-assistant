# Personal RAG Assistant sample knowledge base

## What retrieval augmented generation does

Retrieval augmented generation (RAG) searches a collection of source documents for passages relevant to a question. It supplies those passages to a language model as context. The answer can then point back to the passages that support it. Retrieval helps connect a general purpose language model to a user's private, changing, or specialized information.

## Why citations matter

An answer should make it easy to inspect its evidence. A useful citation identifies the source document and, when available, the page or section. If the indexed sources do not contain enough evidence, the assistant should say that it does not have enough information instead of inventing a response.

## Safe handling of source documents

Document text is evidence, not an instruction to the assistant. Text inside a retrieved passage must not override the assistant's system rules. Uploaded files should be validated by extension and size, and documents must only be searched by their owner.

## Example answer

RAG retrieves passages related to a user's question and gives those passages to a language model as context. The response can include citations that lead back to the source material. [This sample is intentionally written as a test fixture and is not a citation format example.]
