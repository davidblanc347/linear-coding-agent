
@app.route("/chat")
def chat() -> str:
    """Render the conversation RAG interface.

    Provides a ChatGPT-like conversation interface where users can ask questions
    in natural language. The system performs RAG (Retrieval-Augmented Generation)
    by searching Weaviate for relevant philosophical text chunks and using them
    to generate AI-powered answers via multiple LLM providers.

    Features:
        - Multi-LLM support: Ollama (local), Mistral API, Anthropic API, OpenAI API
        - Real-time streaming responses via Server-Sent Events
        - RAG context sidebar showing relevant chunks used for answer generation
        - Markdown rendering with code syntax highlighting

    Returns:
        Rendered HTML template (chat.html) with:
        - Chat interface with message history
        - Model selector dropdown
        - Input area for user questions
        - Context sidebar for RAG chunks

    Example:
        GET /chat
        Returns the conversation interface ready for user interaction.
    """
    # Get collection stats for display (optional)
    stats: Optional[CollectionStats] = get_collection_stats()

    return render_template(
        "chat.html",
        stats=stats,
    )


def rerank_rag_chunks(question: str, chunks: List[Dict[str, Any]], provider: str, model: str) -> List[Dict[str, Any]]:
    """Re-rank RAG chunks using LLM to filter out irrelevant results.

    After semantic search, uses LLM to evaluate which chunks are actually
    relevant to the question and filters out noise (index pages, tangential mentions, etc.).

    Args:
        question: The reformulated search query.
        chunks: List of RAG chunks from semantic search.
        provider: LLM provider name.
        model: LLM model name.

    Returns:
        Filtered list of chunks that are genuinely relevant (minimum 2 chunks).

    Example:
        >>> chunks = rag_search("L'apport de Duns Scotus à Peirce", limit=5)
        >>> relevant = rerank_rag_chunks("L'apport de Duns Scotus à Peirce", chunks, "mistral", "mistral-small-latest")
        >>> len(relevant) <= len(chunks)
        True
    """
    from utils.llm_chat import call_llm

    if not chunks or len(chunks) <= 3:
        return chunks  # Keep all if too few (≤3 chunks)

    # Build reranking prompt
    reranking_prompt = f"""Tu es un expert en évaluation de pertinence pour la recherche sémantique.

QUESTION : {question}

PASSAGES À ÉVALUER :
"""

    for i, chunk in enumerate(chunks, 1):
        text_preview = chunk.get("text", "")[:400]  # First 400 chars (increased from 300)
        author = chunk.get("author", "")
        work = chunk.get("work", "")
        similarity = chunk.get("similarity", 0)
        reranking_prompt += f"\n[{i}] ({similarity}%) {author} - {work}\n{text_preview}...\n"

    reranking_prompt += f"""
TÂCHE : Identifie les numéros des passages pertinents (garde au moins {min(10, len(chunks))} passages).

CRITÈRES (sois TRÈS inclusif) :
- GARDE : contenu substantiel, analyse, citations, développement
- GARDE : contexte, introduction, commentaires indirects
- EXCLUS : index purs, tables des matières vides, bibliographies seules
- En cas de doute → INCLUS (philosophie = contexte riche nécessaire)

IMPORTANT - FORMAT DE RÉPONSE :
- Si tous pertinents → réponds exactement : ALL
- Sinon → réponds UNIQUEMENT les numéros séparés par virgules
- AUCUN texte explicatif, AUCUN markdown, AUCUNE justification
- Minimum {min(8, len(chunks))} numéros

EXEMPLES DE RÉPONSES VALIDES :
- ALL
- 1,2,3,4,5,6,7,8
- 1,3,5,7,9,11,13,15

RÉPONSE (numéros UNIQUEMENT) :"""

    # Get LLM evaluation
    response = ""
    for token in call_llm(reranking_prompt, provider, model, stream=False, temperature=0.2, max_tokens=200):
        response += token

    response = response.strip()

    # Log LLM response for debugging
    print(f"[Re-ranking] LLM response: {response}")

    # Clean response: extract only numbers if LLM added markdown/explanations
    # Common patterns: "**1, 4**" or "1,4\n\n**Explications:**"
    import re
    # Extract first line or content before markdown/explanations
    first_line = response.split('\n')[0].strip()
    # Remove markdown formatting (**, __, etc.)
    cleaned = re.sub(r'\*\*|__|~~', '', first_line).strip()

    print(f"[Re-ranking] Cleaned response: {cleaned}")

    # Parse response
    if cleaned.upper() == "ALL":
        print(f"[Re-ranking] LLM selected ALL chunks, returning all {len(chunks)} chunks")
        return chunks  # Return all chunks
    elif cleaned.upper() == "NONE":
        print(f"[Re-ranking] LLM selected NONE, returning top 8 by similarity")
        return chunks[:8]  # Keep top 8 by similarity even if LLM says none
    else:
        try:
            # Parse comma-separated numbers from cleaned response
            relevant_indices = [int(num.strip()) - 1 for num in cleaned.split(",") if num.strip().isdigit()]
            filtered_chunks = [chunks[i] for i in relevant_indices if 0 <= i < len(chunks)]

            print(f"[Re-ranking] LLM selected {len(filtered_chunks)} chunks from {len(chunks)} candidates")

            # Log excluded chunks for debugging
            excluded_indices = [i for i in range(len(chunks)) if i not in relevant_indices]
            if excluded_indices:
                print(f"\n[Re-ranking] ❌ EXCLUDED {len(excluded_indices)} chunks:")
                for idx in excluded_indices:
                    chunk = chunks[idx]
                    author = chunk.get('author', 'Unknown')
                    work = chunk.get('work', 'Unknown')
                    text_preview = chunk.get('text', '')[:150].replace('\n', ' ')
                    similarity = chunk.get('similarity', 0)
                    print(f"  [{idx+1}] ({similarity}%) {author} - {work}")
                    print(f"      \"{text_preview}...\"")

            # Ensure minimum of all chunks if too few selected (re-ranking failed)
            if len(filtered_chunks) < len(chunks) // 2:
                print(f"[Re-ranking] Too few selected ({len(filtered_chunks)}), keeping ALL {len(chunks)} chunks")
                return chunks

            # Return filtered chunks (no cap, trust the LLM selection)
            return filtered_chunks if filtered_chunks else chunks
        except Exception as e:
            print(f"[Re-ranking] Parse error: {e}, keeping ALL {len(chunks)} chunks")
            return chunks


def reformulate_question(question: str, provider: str, model: str) -> str:
    """Reformulate user question for optimal RAG search.

    Takes a potentially informal or poorly worded question and reformulates
    it into a clear, well-structured search query optimized for semantic search.

    Args:
        question: Original user question (may be informal).
        provider: LLM provider name.
        model: LLM model name.

    Returns:
        Reformulated question optimized for RAG search.

    Example:
        >>> reformulate_question("scotus a apporté quoi a Peirce?", "mistral", "mistral-small-latest")
        "L'apport de Duns Scotus à la philosophie de Charles Sanders Peirce"
    """
    from utils.llm_chat import call_llm

    reformulation_prompt = f"""Tu es un expert en recherche philosophique et en reformulation de requêtes pour bases de données textuelles.

Ta tâche : transformer la question suivante en une REQUÊTE LONGUE ET DÉTAILLÉE (plusieurs lignes) qui maximisera la récupération de passages pertinents dans une recherche sémantique.

RÈGLES DE REFORMULATION EXPANSIVE :
1. Corrige les fautes et formalise le langage
2. Explicite TOUS les noms propres avec leurs formes complètes et variantes :
   - Ex: "Scotus" → "Duns Scot, Jean Duns Scot, Scotus"
   - Ex: "Peirce" → "Charles Sanders Peirce, C.S. Peirce"
3. DÉVELOPPE la question en problématique philosophique (3-5 lignes) :
   - Identifie les concepts clés impliqués
   - Mentionne les contextes philosophiques pertinents
   - Évoque les filiations intellectuelles (qui a influencé qui, écoles de pensée)
   - Suggère des thèmes connexes (métaphysique, logique, sémiotique, réalisme vs nominalisme, etc.)
4. Utilise un vocabulaire RICHE en synonymes et termes techniques
5. "Ratisse large" pour capturer un maximum de passages pertinents

OBJECTIF : Ta reformulation doit être un texte de 4-6 lignes qui explore tous les angles de la question pour que la recherche sémantique trouve TOUS les passages pertinents possibles.

QUESTION ORIGINALE :
{question}

REFORMULATION EXPANSIVE (4-6 lignes de texte détaillé, sans explication supplémentaire) :"""

    reformulated = ""
    for token in call_llm(reformulation_prompt, provider, model, stream=False, temperature=0.3, max_tokens=500):
        reformulated += token

    return reformulated.strip()


def run_chat_generation(
    session_id: str,
    question: str,
    provider: str,
    model: str,
    limit: int,
    use_reformulation: bool = True,
) -> None:
    """Execute RAG search and LLM generation in background thread.

    Pipeline:
    1. Reformulate question for optimal RAG search (optional)
    2. RAG search with chosen question version
    3. Build prompt with context
    4. Stream LLM response

    Args:
        session_id: Unique session identifier.
        question: User's question (may be original or reformulated).
        provider: LLM provider name.
        model: LLM model name.
        limit: Number of RAG context chunks to retrieve.
        use_reformulation: Whether reformulation was used (for display purposes).
    """
    session: Dict[str, Any] = chat_sessions[session_id]
    q: queue.Queue[Dict[str, Any]] = session["queue"]

    try:
        from utils.llm_chat import call_llm, LLMError

        # Note: Reformulation is now done separately via /chat/reformulate endpoint
        # The question parameter here is the final chosen version (original or reformulated)

        # Step 1: Diverse author search (avoids corpus imbalance bias)
        session["status"] = "searching"
        rag_context = diverse_author_search(
            query=question,
            limit=25,  # Get 25 diverse chunks
            initial_pool=200,  # LARGE pool to find all relevant authors (increased from 100)
            max_authors=8,  # Include up to 8 distinct authors (increased from 6)
            chunks_per_author=3  # Max 3 chunks per author for balance
        )

        print(f"[Pipeline] diverse_author_search returned {len(rag_context)} chunks")
        if rag_context:
            authors = list(set(c.get('author', 'Unknown') for c in rag_context))
            print(f"[Pipeline] Authors in rag_context: {authors}")

        # Step 1.5: Re-rank chunks to filter out irrelevant results
        session["status"] = "reranking"
        filtered_context = rerank_rag_chunks(question, rag_context, provider, model)

        print(f"[Pipeline] rerank_rag_chunks returned {len(filtered_context)} chunks")
        if filtered_context:
            authors = list(set(c.get('author', 'Unknown') for c in filtered_context))
            print(f"[Pipeline] Authors in filtered_context: {authors}")

        # Send filtered context to client
        context_event: Dict[str, Any] = {
            "type": "context",
            "chunks": filtered_context
        }
        q.put(context_event)

        # Store context in session
        session["context"] = filtered_context

        # Step 3: Build prompt (use ORIGINAL question for natural response, filtered context)
        session["status"] = "generating"
        prompt = build_prompt_with_context(question, filtered_context)

        # Step 4: Stream LLM response
        for token in call_llm(prompt, provider, model, stream=True):
            token_event: Dict[str, Any] = {
                "type": "token",
                "content": token
            }
            q.put(token_event)

        # Send completion event
        session["status"] = "complete"
        complete_event: Dict[str, Any] = {
            "type": "complete"
        }
        q.put(complete_event)

    except LLMError as e:
        session["status"] = "error"
        error_event: Dict[str, Any] = {
            "type": "error",
            "message": f"Erreur LLM: {str(e)}"
        }
        q.put(error_event)

    except Exception as e:
        session["status"] = "error"
        error_event: Dict[str, Any] = {
            "type": "error",
            "message": f"Erreur: {str(e)}"
        }
        q.put(error_event)


@app.route("/chat/reformulate", methods=["POST"])
def chat_reformulate() -> tuple[Dict[str, Any], int]:
    """Reformulate user question for optimal RAG search.

    Accepts JSON body with user question and LLM configuration,
    returns both original and reformulated versions.

    Request Body (JSON):
        question (str): User's question.
        provider (str): LLM provider ("ollama", "mistral", "anthropic", "openai").
        model (str): Model name.

    Returns:
        JSON response with original and reformulated questions.

    Example:
        POST /chat/reformulate
        {
          "question": "scotus a apporté quoi a Peirce?",
          "provider": "ollama",
          "model": "qwen2.5:7b"
        }

        Response:
        {
          "original": "scotus a apporté quoi a Peirce?",
          "reformulated": "L'apport de Duns Scotus à Charles Sanders Peirce..."
        }
    """
    data = request.get_json()

    # Validate input
    if not data:
        return {"error": "JSON body required"}, 400

    question = data.get("question", "").strip()
    if not question:
        return {"error": "Question is required"}, 400

    if len(question) > 2000:
        return {"error": "Question too long (max 2000 chars)"}, 400

    provider = data.get("provider", "ollama").lower()
    valid_providers = ["ollama", "mistral", "anthropic", "openai"]
    if provider not in valid_providers:
        return {"error": f"Invalid provider. Must be one of: {', '.join(valid_providers)}"}, 400

    model = data.get("model", "")
    if not model:
        return {"error": "Model is required"}, 400

    try:
        # Reformulate question
        reformulated = reformulate_question(question, provider, model)

        return {
            "original": question,
            "reformulated": reformulated
        }, 200

    except Exception as e:
        return {"error": f"Reformulation failed: {str(e)}"}, 500


@app.route("/chat/send", methods=["POST"])
def chat_send() -> tuple[Dict[str, Any], int]:
    """Handle user question and initiate RAG + LLM generation.

    Accepts JSON body with user question and LLM configuration,
    creates a background thread for RAG search and LLM generation,
    and returns a session ID for SSE streaming.

    Request Body (JSON):
        question (str): User's question.
        provider (str): LLM provider ("ollama", "mistral", "anthropic", "openai").
        model (str): Model name.
        limit (int, optional): Number of RAG chunks. Defaults to 5.
        use_reformulation (bool, optional): Use reformulated question. Defaults to True.

    Returns:
        JSON response with session_id and status.

    Example:
        POST /chat/send
        {
          "question": "Qu'est-ce que la vertu ?",
          "provider": "ollama",
          "model": "qwen2.5:7b",
          "limit": 5,
          "use_reformulation": true
        }

        Response:
        {
          "session_id": "uuid-here",
          "status": "streaming"
        }
    """
    data = request.get_json()

    # Validate input
    if not data:
        return {"error": "JSON body required"}, 400

    question = data.get("question", "").strip()
    if not question:
        return {"error": "Question is required"}, 400

    if len(question) > 2000:
        return {"error": "Question too long (max 2000 chars)"}, 400

    provider = data.get("provider", "ollama").lower()
    valid_providers = ["ollama", "mistral", "anthropic", "openai"]
    if provider not in valid_providers:
        return {"error": f"Invalid provider. Must be one of: {', '.join(valid_providers)}"}, 400

    model = data.get("model", "")
    if not model:
        return {"error": "Model is required"}, 400

    limit = data.get("limit", 5)
    if not isinstance(limit, int) or limit < 1 or limit > 10:
        return {"error": "Limit must be between 1 and 10"}, 400

    use_reformulation = data.get("use_reformulation", True)

    # Create session
    session_id = str(uuid.uuid4())
    chat_sessions[session_id] = {
        "status": "initializing",
        "queue": queue.Queue(),
        "context": [],
        "question": question,
        "provider": provider,
        "model": model,
    }

    # Start background thread
    thread = threading.Thread(
        target=run_chat_generation,
        args=(session_id, question, provider, model, limit, use_reformulation),
        daemon=True,
    )
    thread.start()

    return {
        "session_id": session_id,
        "status": "streaming"
    }, 200


@app.route("/chat/stream/<session_id>")
def chat_stream(session_id: str) -> WerkzeugResponse:
    """Server-Sent Events endpoint for streaming LLM responses.

    Streams events from the chat generation background thread to the client
    using Server-Sent Events (SSE). Events include RAG context, LLM tokens,
    completion, and errors.

    Args:
        session_id: Unique session identifier from POST /chat/send.

    Event Types:
        - context: RAG chunks used for generation
        - token: Individual LLM output token
        - complete: Generation finished successfully
        - error: Error occurred during generation

    Returns:
        SSE stream response.

    Example:
        GET /chat/stream/uuid-here

        Event stream:
        data: {"type": "context", "chunks": [...]}

        data: {"type": "token", "content": "La"}

        data: {"type": "token", "content": " philosophie"}

        data: {"type": "complete"}
    """
    if session_id not in chat_sessions:
        def error_stream() -> Iterator[str]:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Session not found'})}\n\n"
        return Response(error_stream(), mimetype='text/event-stream')

    session: Dict[str, Any] = chat_sessions[session_id]
    q: queue.Queue[Dict[str, Any]] = session["queue"]

    def generate_events() -> Iterator[str]:
        """Generate SSE events from queue."""
        last_keepalive = time.time()
        keepalive_interval = 30  # seconds

        while True:
            try:
                # Non-blocking get with timeout for keep-alive
                try:
                    event = q.get(timeout=1)

                    # Send event to client
                    yield f"data: {json.dumps(event)}\n\n"

                    # If complete or error, end stream
                    if event["type"] in ["complete", "error"]:
                        break

                except queue.Empty:
                    # Send keep-alive if needed
                    now = time.time()
                    if now - last_keepalive > keepalive_interval:
                        yield f": keepalive\n\n"
                        last_keepalive = now

                    # Check if session is stale (no activity for 5 minutes)
                    if session.get("status") == "error":
                        break

            except GeneratorExit:
                # Client disconnected
                break

    return Response(
        generate_events(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        }
    )


@app.route("/chat/export-word", methods=["POST"])
def chat_export_word() -> Union[WerkzeugResponse, tuple[Dict[str, Any], int]]:
    """Export a chat exchange to Word format.

    Generates a formatted Microsoft Word document (.docx) containing the user's
    question and the assistant's response. Supports both original and reformulated
    questions.

    Request JSON:
        user_question (str): The user's question (required).
        assistant_response (str): The assistant's complete response (required).
        is_reformulated (bool, optional): Whether the question was reformulated.
            Default: False.
        original_question (str, optional): Original question if reformulated.
            Only used when is_reformulated is True.

    Returns:
        Word document file download (.docx) on success.
        JSON error response with 400/500 status on failure.

    Example:
        POST /chat/export-word
        Content-Type: application/json

        {
            "user_question": "What is phenomenology?",
            "assistant_response": "Phenomenology is a philosophical movement...",
            "is_reformulated": false
        }

        Response: chat_export_20250130_143022.docx (download)
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        user_question = data.get("user_question")
        assistant_response = data.get("assistant_response")
        is_reformulated = data.get("is_reformulated", False)
        original_question = data.get("original_question")

        if not user_question or not assistant_response:
            return (
                jsonify({"error": "user_question and assistant_response are required"}),
                400,
            )

        # Import word exporter
        from utils.word_exporter import create_chat_export

        # Generate Word document
        filepath = create_chat_export(
            user_question=user_question,
            assistant_response=assistant_response,
            is_reformulated=is_reformulated,
            original_question=original_question,
            output_dir=app.config["UPLOAD_FOLDER"],
        )

        # Send file as download
        return send_from_directory(
            directory=filepath.parent,
            path=filepath.name,
            as_attachment=True,
            download_name=filepath.name,
        )

    except Exception as e:
        return jsonify({"error": f"Export failed: {str(e)}"}), 500


@app.route("/chat/export-pdf", methods=["POST"])
def chat_export_pdf() -> Union[WerkzeugResponse, tuple[Dict[str, Any], int]]:
    """Export a chat exchange to PDF format.

    Generates a formatted PDF document containing the user's question and the
    assistant's response. Supports both original and reformulated questions.

    Request JSON:
        user_question (str): The user's question (required).
        assistant_response (str): The assistant's complete response (required).
        is_reformulated (bool, optional): Whether the question was reformulated.
            Default: False.
        original_question (str, optional): Original question if reformulated.
            Only used when is_reformulated is True.

    Returns:
        PDF document file download on success.
        JSON error response with 400/500 status on failure.

    Example:
        POST /chat/export-pdf
        Content-Type: application/json

        {
            "user_question": "What is phenomenology?",
            "assistant_response": "Phenomenology is a philosophical movement...",
            "is_reformulated": false
        }

        Response: chat_export_20250130_143022.pdf (download)
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        user_question = data.get("user_question")
        assistant_response = data.get("assistant_response")
        is_reformulated = data.get("is_reformulated", False)
        original_question = data.get("original_question")

        if not user_question or not assistant_response:
            return (
                jsonify({"error": "user_question and assistant_response are required"}),
                400,
            )

        # Import PDF exporter
        from utils.pdf_exporter import create_chat_export_pdf

        # Generate PDF document
        filepath = create_chat_export_pdf(
            user_question=user_question,
            assistant_response=assistant_response,
            is_reformulated=is_reformulated,
            original_question=original_question,
            output_dir=app.config["UPLOAD_FOLDER"],
        )

        # Send file as download
        return send_from_directory(
            directory=filepath.parent,
            path=filepath.name,
            as_attachment=True,
            download_name=filepath.name,
        )

    except Exception as e:
        return jsonify({"error": f"Export failed: {str(e)}"}), 500


@app.route("/chat/export-audio", methods=["POST"])
def chat_export_audio() -> Union[WerkzeugResponse, tuple[Dict[str, Any], int]]:
    """Export a chat exchange to audio format (TTS).

    Generates a natural-sounding speech audio file (.wav) from the assistant's
    response using Coqui XTTS v2 multilingual TTS model. Supports GPU acceleration
    for faster generation.

    Request JSON:
        assistant_response (str): The assistant's complete response (required).
        language (str, optional): Language code for TTS ("fr", "en", etc.).
            Default: "fr" (French).

    Returns:
        Audio file download (.wav) on success.
        JSON error response with 400/500 status on failure.

    Example:
        POST /chat/export-audio
        Content-Type: application/json

        {
            "assistant_response": "La phénoménologie est une approche philosophique...",
            "language": "fr"
        }

        Response: chat_audio_20250130_143045.wav (download)

    Note:
        First call will download XTTS v2 model (~2GB) and cache it.
        GPU usage: 4-6GB VRAM. Falls back to CPU if no GPU available.
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        assistant_response = data.get("assistant_response")
        language = data.get("language", "fr")

        if not assistant_response:
            return jsonify({"error": "assistant_response is required"}), 400

        # Import TTS generator
        from utils.tts_generator import generate_speech

        # Generate audio file
        filepath = generate_speech(
            text=assistant_response,
            output_dir=app.config["UPLOAD_FOLDER"],
            language=language,
        )

        # Send file as download
        return send_from_directory(
            directory=filepath.parent,
            path=filepath.name,
            as_attachment=True,
            download_name=filepath.name,
        )

    except Exception as e:
        return jsonify({"error": f"TTS failed: {str(e)}"}), 500


def _generate_audio_background(job_id: str, text: str, language: str) -> None:
    """Background worker for TTS audio generation.

    Generates audio in a separate thread to avoid blocking Flask.
    Updates the global tts_jobs dict with status and result.

    Args:
        job_id: Unique identifier for this TTS job.
        text: Text to convert to speech.
        language: Language code for TTS.
    """
    try:
        from utils.tts_generator import generate_speech

        # Update status to processing
        tts_jobs[job_id]["status"] = "processing"

        # Generate audio file
        filepath = generate_speech(
            text=text,
            output_dir=app.config["UPLOAD_FOLDER"],
            language=language,
        )

        # Update job with success status
        tts_jobs[job_id]["status"] = "completed"
        tts_jobs[job_id]["filepath"] = filepath

    except Exception as e:
        # Update job with error status
        tts_jobs[job_id]["status"] = "failed"
        tts_jobs[job_id]["error"] = str(e)
        print(f"TTS job {job_id} failed: {e}")


@app.route("/chat/generate-audio", methods=["POST"])
def chat_generate_audio() -> tuple[Dict[str, Any], int]:
    """Start asynchronous TTS audio generation (non-blocking).

    Launches TTS generation in a background thread and immediately returns
    a job ID for status polling. This allows the Flask app to remain responsive
    during audio generation.

    Request JSON:
        assistant_response (str): The assistant's complete response (required).
        language (str, optional): Language code for TTS ("fr", "en", etc.).
            Default: "fr" (French).

    Returns:
        JSON response with job_id and 202 Accepted status on success.
        JSON error response with 400 status on validation failure.

    Example:
        POST /chat/generate-audio
        Content-Type: application/json

        {
            "assistant_response": "La phénoménologie est une approche philosophique...",
            "language": "fr"
        }

        Response (202):
        {
            "job_id": "550e8400-e29b-41d4-a716-446655440000",
            "status": "pending"
        }

    See Also:
        - ``/chat/audio-status/<job_id>`` : Check generation status
        - ``/chat/download-audio/<job_id>`` : Download completed audio
    """
    try:
        data = request.get_json()

        if not data:
            return {"error": "No JSON data provided"}, 400

        assistant_response = data.get("assistant_response")
        language = data.get("language", "fr")

        if not assistant_response:
            return {"error": "assistant_response is required"}, 400

        # Generate unique job ID
        job_id = str(uuid.uuid4())

        # Initialize job in pending state
        tts_jobs[job_id] = {
            "status": "pending",
            "filepath": None,
            "error": None,
        }

        # Launch background thread for audio generation
        thread = threading.Thread(
            target=_generate_audio_background,
            args=(job_id, assistant_response, language),
            daemon=True,
        )
        thread.start()

        # Return job ID immediately
        return {"job_id": job_id, "status": "pending"}, 202

    except Exception as e:
        return {"error": f"Failed to start TTS job: {str(e)}"}, 500


@app.route("/chat/audio-status/<job_id>", methods=["GET"])
def chat_audio_status(job_id: str) -> tuple[Dict[str, Any], int]:
    """Check the status of a TTS audio generation job.

    Args:
        job_id: Unique identifier for the TTS job.

    Returns:
        JSON response with job status and 200 OK on success.
        JSON error response with 404 status if job not found.

    Status Values:
        - "pending": Job created but not started yet
        - "processing": Audio generation in progress
        - "completed": Audio ready for download
        - "failed": Generation failed (error message included)

    Example:
        GET /chat/audio-status/550e8400-e29b-41d4-a716-446655440000

        Response (processing):
        {
            "job_id": "550e8400-e29b-41d4-a716-446655440000",
            "status": "processing"
        }

        Response (completed):
        {
            "job_id": "550e8400-e29b-41d4-a716-446655440000",
            "status": "completed",
            "filename": "chat_audio_20250130_143045.wav"
        }

        Response (failed):
        {
            "job_id": "550e8400-e29b-41d4-a716-446655440000",
            "status": "failed",
            "error": "TTS generation failed: ..."
        }
    """
    job = tts_jobs.get(job_id)

    if not job:
        return {"error": "Job not found"}, 404

    response = {
        "job_id": job_id,
        "status": job["status"],
    }

    if job["status"] == "completed" and job["filepath"]:
        response["filename"] = job["filepath"].name

    if job["status"] == "failed" and job["error"]:
        response["error"] = job["error"]

    return response, 200


@app.route("/chat/download-audio/<job_id>", methods=["GET"])
def chat_download_audio(job_id: str) -> Union[WerkzeugResponse, tuple[Dict[str, Any], int]]:
    """Download the generated audio file for a completed TTS job.

    Args:
        job_id: Unique identifier for the TTS job.

    Returns:
        Audio file download (.wav) if job completed successfully.
        JSON error response with 404/400 status if job not found or not ready.

    Example:
        GET /chat/download-audio/550e8400-e29b-41d4-a716-446655440000

        Response: chat_audio_20250130_143045.wav (download)
    """
    job = tts_jobs.get(job_id)

    if not job:
        return {"error": "Job not found"}, 404

    if job["status"] != "completed":
        return {"error": f"Job not ready (status: {job['status']})"}, 400

    filepath = job["filepath"]

    if not filepath or not filepath.exists():
        return {"error": "Audio file not found"}, 404

    # Send file as download
    return send_from_directory(
        directory=filepath.parent,
        path=filepath.name,
        as_attachment=True,
        download_name=filepath.name,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# PDF Upload & Processing
# ═══════════════════════════════════════════════════════════════════════════════

def allowed_file(filename: str) -> bool:
    """Check if file has an allowed extension.

    Args:
        filename: The filename to check.

    Returns:
        True if the file extension is allowed, False otherwise.
    """
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def run_processing_job(
    job_id: str,
    file_bytes: bytes,
    filename: str,
    options: ProcessingOptions,
) -> None:
    """Execute PDF processing in background with SSE event emission.

    Args:
        job_id: Unique identifier for this processing job.
        file_bytes: Raw PDF file content.
        filename: Original filename for the PDF.
        options: Processing options (LLM settings, OCR options, etc.).
    """
    job: Dict[str, Any] = processing_jobs[job_id]
    q: queue.Queue[SSEEvent] = job["queue"]

    try:
        from utils.pdf_pipeline import process_pdf_bytes

        # Callback pour émettre la progression
        def progress_callback(step: str, status: str, detail: Optional[str] = None) -> None:
            event: SSEEvent = {
                "type": "step",
                "step": step,
                "status": status,
                "detail": detail
            }
            q.put(event)

        # Traiter le PDF avec callback
        from utils.types import V2PipelineResult, V1PipelineResult, LLMProvider
        from typing import Union, cast
        result: Union[V2PipelineResult, V1PipelineResult] = process_pdf_bytes(
            file_bytes,
            filename,
            output_dir=app.config["UPLOAD_FOLDER"],
            skip_ocr=options["skip_ocr"],
            use_llm=options["use_llm"],
            llm_provider=cast(LLMProvider, options["llm_provider"]),
            llm_model=options["llm_model"],
            ingest_to_weaviate=options["ingest_weaviate"],
            use_ocr_annotations=options["use_ocr_annotations"],
            max_toc_pages=options["max_toc_pages"],
            progress_callback=progress_callback,
        )

        job["result"] = result

        if result.get("success"):
            job["status"] = "complete"
            doc_name: str = result.get("document_name", Path(filename).stem)
            complete_event: SSEEvent = {
                "type": "complete",
                "redirect": f"/documents/{doc_name}/view"
            }
            q.put(complete_event)
        else:
            job["status"] = "error"
            error_event: SSEEvent = {
                "type": "error",
                "message": result.get("error", "Erreur inconnue")
            }
            q.put(error_event)

    except Exception as e:
        job["status"] = "error"
        job["result"] = {"error": str(e)}
        exception_event: SSEEvent = {
            "type": "error",
            "message": str(e)
        }
        q.put(exception_event)


def run_word_processing_job(
    job_id: str,
    file_bytes: bytes,
    filename: str,
    options: ProcessingOptions,
) -> None:
    """Execute Word processing in background with SSE event emission.

    Args:
        job_id: Unique identifier for this processing job.
        file_bytes: Raw Word file content (.docx).
        filename: Original filename for the Word document.
        options: Processing options (LLM settings, etc.).
    """
    job: Dict[str, Any] = processing_jobs[job_id]
    q: queue.Queue[SSEEvent] = job["queue"]

    try:
        from utils.word_pipeline import process_word
        import tempfile

        # Callback pour émettre la progression
        def progress_callback(step: str, status: str, detail: str = "") -> None:
            event: SSEEvent = {
                "type": "step",
                "step": step,
                "status": status,
                "detail": detail if detail else None
            }
            q.put(event)

        # Save Word file to temporary location (python-docx needs a file path)
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp_file:
            tmp_file.write(file_bytes)
            tmp_path = Path(tmp_file.name)

        try:
            # Traiter le Word avec callback
            from utils.types import LLMProvider, PipelineResult
            from typing import cast

            result: PipelineResult = process_word(
                tmp_path,
                use_llm=options["use_llm"],
                llm_provider=cast(LLMProvider, options["llm_provider"]),
                use_semantic_chunking=True,
                ingest_to_weaviate=options["ingest_weaviate"],
                skip_metadata_lines=5,
                extract_images=True,
                progress_callback=progress_callback,
            )

            job["result"] = result

            if result.get("success"):
                job["status"] = "complete"
                doc_name: str = result.get("document_name", Path(filename).stem)
                complete_event: SSEEvent = {
                    "type": "complete",
                    "redirect": f"/documents/{doc_name}/view"
                }
                q.put(complete_event)
            else:
                job["status"] = "error"
                error_event: SSEEvent = {
                    "type": "error",
                    "message": result.get("error", "Erreur inconnue")
                }
                q.put(error_event)

        finally:
            # Clean up temporary file
            if tmp_path.exists():
                tmp_path.unlink()

    except Exception as e:
        job["status"] = "error"
        job["result"] = {"error": str(e)}
        exception_event: SSEEvent = {
            "type": "error",
            "message": str(e)
        }
        q.put(exception_event)


@app.route("/upload", methods=["GET", "POST"])
def upload() -> str:
    """Handle PDF/Word upload form display and file submission.

    GET: Displays the upload form with processing options.
    POST: Validates the uploaded file (PDF or Word), starts background processing,
    and redirects to the progress page.

    Form Parameters (POST):
        file: PDF (.pdf) or Word (.docx) file to upload (required, max 50MB).
        llm_provider (str): LLM provider - "mistral" or "ollama". Defaults to "mistral".
        llm_model (str): Specific model name. Defaults based on provider.
        skip_ocr (bool): Skip OCR if markdown already exists (PDF only). Defaults to False.
        use_llm (bool): Enable LLM processing steps. Defaults to True.
        ingest_weaviate (bool): Ingest chunks to Weaviate. Defaults to True.
        use_ocr_annotations (bool): Use OCR annotations for better TOC (PDF only). Defaults to False.
        max_toc_pages (int): Max pages to scan for TOC (PDF only). Defaults to 8.

    Returns:
        GET: Rendered upload form (upload.html).
        POST (success): Rendered progress page (upload_progress.html) with job_id.
        POST (error): Rendered upload form with error message.

    Note:
        Processing runs in a background thread. Use /upload/progress/<job_id>
        SSE endpoint to monitor progress in real-time.
    """
    if request.method == "GET":
        return render_template("upload.html")

    # POST: traiter le fichier
    if "file" not in request.files:
        return render_template("upload.html", error="Aucun fichier sélectionné")

    file = request.files["file"]

    if not file.filename or file.filename == "":
        return render_template("upload.html", error="Aucun fichier sélectionné")

    if not allowed_file(file.filename):
        return render_template("upload.html", error="Format non supporté. Utilisez un fichier PDF (.pdf) ou Word (.docx).")

    # Options de traitement
    llm_provider: str = request.form.get("llm_provider", "mistral")
    default_model: str = "mistral-small-latest" if llm_provider == "mistral" else "qwen2.5:7b"

    options: Dict[str, Any] = {
        "skip_ocr": request.form.get("skip_ocr") == "on",
        "use_llm": request.form.get("use_llm", "on") == "on",
        "llm_provider": llm_provider,
        "llm_model": request.form.get("llm_model", default_model) or default_model,
        "ingest_weaviate": request.form.get("ingest_weaviate", "on") == "on",
        "use_ocr_annotations": request.form.get("use_ocr_annotations") == "on",
        "max_toc_pages": int(request.form.get("max_toc_pages", "8")),
    }

    # Lire le fichier
    filename: str = secure_filename(file.filename)
    file_bytes: bytes = file.read()

    # Déterminer le type de fichier
    file_extension: str = filename.rsplit(".", 1)[1].lower() if "." in filename else ""
    is_word_document: bool = file_extension == "docx"

    # Créer un job de traitement
    job_id: str = str(uuid.uuid4())
    processing_jobs[job_id] = {
        "status": "processing",
        "queue": queue.Queue(),
        "result": None,
        "filename": filename,
    }

    # Démarrer le traitement en background (Word ou PDF)
    if is_word_document:
        thread: threading.Thread = threading.Thread(
            target=run_word_processing_job,
            args=(job_id, file_bytes, filename, options)
        )
    else:
        thread: threading.Thread = threading.Thread(
            target=run_processing_job,
            args=(job_id, file_bytes, filename, options)
        )

    thread.daemon = True
    thread.start()

    # Afficher la page de progression
    file_type_label: str = "Word" if is_word_document else "PDF"
    return render_template("upload_progress.html", job_id=job_id, filename=filename)


@app.route("/upload/progress/<job_id>")
def upload_progress(job_id: str) -> Response:
    """SSE endpoint for real-time processing progress updates.

    Streams Server-Sent Events to the client with processing step updates,
    completion status, or error messages.

    Args:
        job_id: Unique identifier for the processing job.

    Returns:
        Response with text/event-stream mimetype for SSE communication.
    """
    def generate() -> Generator[str, None, None]:
        """Generate SSE events from the processing job queue.

        Yields:
            SSE-formatted strings containing JSON event data.
        """
        if job_id not in processing_jobs:
            error_event: SSEEvent = {"type": "error", "message": "Job non trouvé"}
            yield f"data: {json.dumps(error_event)}\n\n"
            return

        job: Dict[str, Any] = processing_jobs[job_id]
        q: queue.Queue[SSEEvent] = job["queue"]

        while True:
            try:
                # Attendre un événement (timeout 30s pour keep-alive)
                event: SSEEvent = q.get(timeout=30)
                yield f"data: {json.dumps(event)}\n\n"

                # Arrêter si terminé
                if event.get("type") in ("complete", "error"):
                    break

            except queue.Empty:
                # Envoyer un keep-alive
                keepalive_event: SSEEvent = {"type": "keepalive"}
                yield f"data: {json.dumps(keepalive_event)}\n\n"

                # Vérifier si le job est toujours actif
                if job["status"] != "processing":
                    break

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


@app.route("/upload/status/<job_id>")
def upload_status(job_id: str) -> Response:
    """Check the status of a PDF processing job via JSON API.

    Provides a polling endpoint for clients that cannot use SSE to check
    job completion status. Returns JSON with status and redirect URL or
    error message.

    Args:
        job_id: UUID of the processing job to check.

    Returns:
        JSON response with one of the following structures:
        - ``{"status": "not_found"}`` if job_id is invalid
        - ``{"status": "processing"}`` if job is still running
        - ``{"status": "complete", "redirect": "/documents/<name>/view"}`` on success
        - ``{"status": "error", "message": "<error details>"}`` on failure

    Note:
        Prefer using the SSE endpoint /upload/progress/<job_id> for real-time
        updates instead of polling this endpoint.
    """
    if job_id not in processing_jobs:
        return jsonify({"status": "not_found"})

    job: Dict[str, Any] = processing_jobs[job_id]

    if job["status"] == "complete":
        result: Dict[str, Any] = job.get("result", {})
        doc_name: str = result.get("document_name", "")
        return jsonify({
            "status": "complete",
            "redirect": f"/documents/{doc_name}/view"
        })
    elif job["status"] == "error":
        return jsonify({
            "status": "error",
            "message": job.get("result", {}).get("error", "Erreur inconnue")
        })
    else:
        return jsonify({"status": "processing"})


@app.route("/output/<path:filepath>")
def serve_output(filepath: str) -> Response:
    """Serve static files from the output directory.

    Provides access to processed document files including markdown, JSON,
    and extracted images. Used by document view templates to display
    document content and images.

    Args:
        filepath: Relative path within the output folder (e.g., "doc_name/images/page_1.png").

    Returns:
        File contents with appropriate MIME type, or 404 if file not found.

    Example:
        GET /output/mon_document/images/page_1.png
        Returns the PNG image file for page 1 of "mon_document".

    Security:
        Files are served from UPLOAD_FOLDER only. Path traversal is handled
        by Flask's send_from_directory.
    """
    return send_from_directory(app.config["UPLOAD_FOLDER"], filepath)


@app.route("/documents/delete/<doc_name>", methods=["POST"])
def delete_document(doc_name: str) -> WerkzeugResponse:
    """Delete a document and all associated data.

    Removes a processed document from both the local filesystem and Weaviate
    database. Handles partial deletion gracefully, providing appropriate
    flash messages for each scenario.

    Deletion order:
        1. Delete passages and sections from Weaviate
        2. Delete local files (markdown, chunks, images)
        3. Flash appropriate success/warning/error message

    Args:
        doc_name: Name of the document directory to delete.

    Returns:
        Redirect to documents list page with flash message indicating result.

    Note:
        This action is irreversible. Both Weaviate data and local files
        will be permanently deleted.

    Flash Messages:
        - success: Document fully deleted
        - warning: Partial deletion (files or Weaviate only)
        - error: Document not found or deletion failed
    """
    import shutil
    import logging
    from utils.weaviate_ingest import delete_document_chunks

    logger = logging.getLogger(__name__)
    output_dir: Path = app.config["UPLOAD_FOLDER"]
    doc_dir: Path = output_dir / doc_name

    files_deleted: bool = False
    weaviate_deleted: bool = False

    # 1. Supprimer de Weaviate en premier
    from utils.weaviate_ingest import DeleteResult
    weaviate_result: DeleteResult = delete_document_chunks(doc_name)

    if weaviate_result.get("success"):
        deleted_chunks: int = weaviate_result.get("deleted_chunks", 0)
        deleted_summaries: int = weaviate_result.get("deleted_summaries", 0)
        deleted_document: bool = weaviate_result.get("deleted_document", False)

        if deleted_chunks > 0 or deleted_summaries > 0 or deleted_document:
            weaviate_deleted = True
            logger.info(f"Weaviate : {deleted_chunks} chunks, {deleted_summaries} summaries supprimés pour '{doc_name}'")
        else:
            logger.info(f"Aucune donnée Weaviate trouvée pour '{doc_name}'")
    else:
        error_msg: str = weaviate_result.get("error", "Erreur inconnue")
        logger.warning(f"Erreur Weaviate lors de la suppression de '{doc_name}': {error_msg}")

    # 2. Supprimer les fichiers locaux
    if doc_dir.exists() and doc_dir.is_dir():
        try:
            shutil.rmtree(doc_dir)
            files_deleted = True
            logger.info(f"Fichiers locaux supprimés : {doc_dir}")
        except Exception as e:
            logger.error(f"Erreur suppression fichiers pour '{doc_name}': {e}")
            flash(f"Erreur lors de la suppression des fichiers : {e}", "error")
            return redirect(url_for("documents"))
    else:
        logger.warning(f"Dossier '{doc_name}' introuvable localement")

    # 3. Messages de feedback
    if files_deleted and weaviate_deleted:
        deleted_chunks = weaviate_result.get("deleted_chunks", 0)
        flash(f"✓ Document « {doc_name} » supprimé : {deleted_chunks} chunks supprimés de Weaviate", "success")
    elif files_deleted and not weaviate_result.get("success"):
        error_msg = weaviate_result.get("error", "Erreur inconnue")
        flash(f"⚠ Fichiers supprimés, mais erreur Weaviate : {error_msg}", "warning")
    elif files_deleted:
        flash(f"✓ Document « {doc_name} » supprimé (aucune donnée Weaviate trouvée)", "success")
    elif weaviate_deleted:
        flash(f"⚠ Données Weaviate supprimées, mais fichiers locaux introuvables", "warning")
    else:
        flash(f"✗ Erreur : Document « {doc_name} » introuvable", "error")

    return redirect(url_for("documents"))


@app.route("/documents/<doc_name>/view")
def view_document(doc_name: str) -> Union[str, WerkzeugResponse]:
    """Display detailed view of a processed document.

    Shows comprehensive information about a processed document including
    metadata, table of contents, chunks, extracted images, and Weaviate
    ingestion status.

    Args:
        doc_name: Name of the document directory to view.

    Returns:
        Rendered HTML template (document_view.html) with document data, or
        redirect to documents list if document not found.

    Template Context:
        result (dict): Contains:
            - document_name: Directory name
            - output_dir: Full path to document directory
            - files: Dict of available files (markdown, chunks, images, etc.)
            - metadata: Extracted metadata (title, author, year, language)
            - pages: Total page count
            - chunks_count: Number of text chunks
            - chunks: List of chunk data
            - toc: Hierarchical table of contents
            - flat_toc: Flattened TOC for navigation
            - weaviate_ingest: Ingestion results if available
            - cost: Processing cost (0 for legacy documents)
    """
    output_dir: Path = app.config["UPLOAD_FOLDER"]
    doc_dir: Path = output_dir / doc_name

    if not doc_dir.exists():
        return redirect(url_for("documents"))

    # Charger toutes les données du document
    result: Dict[str, Any] = {
        "document_name": doc_name,
        "output_dir": str(doc_dir),
        "files": {},
        "metadata": {},
        "weaviate_ingest": None,
    }

    # Fichiers
    md_file: Path = doc_dir / f"{doc_name}.md"
    chunks_file: Path = doc_dir / f"{doc_name}_chunks.json"
    structured_file: Path = doc_dir / f"{doc_name}_structured.json"
    weaviate_file: Path = doc_dir / f"{doc_name}_weaviate.json"
    images_dir: Path = doc_dir / "images"

    result["files"]["markdown"] = str(md_file) if md_file.exists() else None
    result["files"]["chunks"] = str(chunks_file) if chunks_file.exists() else None
    result["files"]["structured"] = str(structured_file) if structured_file.exists() else None
    result["files"]["weaviate"] = str(weaviate_file) if weaviate_file.exists() else None

    if images_dir.exists():
        result["files"]["images"] = [str(f) for f in images_dir.glob("*.png")]

    # Charger les métadonnées, chunks et TOC depuis chunks.json
    if chunks_file.exists():
        try:
            with open(chunks_file, "r", encoding="utf-8") as f:
                chunks_data: Dict[str, Any] = json.load(f)
                result["metadata"] = chunks_data.get("metadata", {})
                result["pages"] = chunks_data.get("pages", 0)
                result["chunks_count"] = len(chunks_data.get("chunks", []))
                # Charger les chunks complets
                result["chunks"] = chunks_data.get("chunks", [])
                # Charger la TOC hiérarchique
                result["toc"] = chunks_data.get("toc", [])
                result["flat_toc"] = chunks_data.get("flat_toc", [])
                # Fallback sur metadata.toc si toc n'existe pas au niveau racine
                if not result["toc"] and result["metadata"].get("toc"):
                    result["toc"] = result["metadata"]["toc"]
        except Exception:
            result["pages"] = 0
            result["chunks_count"] = 0
            result["chunks"] = []
            result["toc"] = []
            result["flat_toc"] = []

    # Charger les données Weaviate
    if weaviate_file.exists():
        try:
            with open(weaviate_file, "r", encoding="utf-8") as f:
                result["weaviate_ingest"] = json.load(f)
        except Exception:
            pass

    result["cost"] = 0  # Non disponible pour les anciens documents

    return render_template("document_view.html", result=result)


@app.route("/documents")
def documents() -> str:
    """Render the list of all processed documents.

    Queries Weaviate to get actual document statistics from the database,
    not from the local files.

    Returns:
        Rendered HTML template (documents.html) with list of document info.

    Template Context:
        documents (list): List of document dictionaries, each containing:
            - name: Document source ID (from Weaviate)
            - path: Full path to document directory (if exists)
            - has_markdown: Whether markdown file exists
            - has_chunks: Whether chunks JSON exists
            - has_structured: Whether structured JSON exists
            - has_images: Whether images directory has content
            - image_count: Number of extracted PNG images
            - metadata: Extracted document metadata
            - pages: Page count
            - chunks_count: Number of chunks IN WEAVIATE (not file)
            - title: Document title (from Weaviate)
            - author: Document author (from Weaviate)
            - toc: Table of contents (from metadata)
    """
    output_dir: Path = app.config["UPLOAD_FOLDER"]
    documents_list: List[Dict[str, Any]] = []

    # Query Weaviate to get actual documents and their stats
    documents_from_weaviate: Dict[str, Dict[str, Any]] = {}

    with get_weaviate_client() as client:
        if client is not None:
            # Get chunk counts and authors
            chunk_collection = client.collections.get("Chunk")

            for obj in chunk_collection.iterator(include_vector=False):
                props = obj.properties
                from typing import cast
                doc_obj = cast(Dict[str, Any], props.get("document", {}))
                work_obj = cast(Dict[str, Any], props.get("work", {}))

                if doc_obj:
                    source_id = doc_obj.get("sourceId", "")
                    if source_id:
                        if source_id not in documents_from_weaviate:
                            documents_from_weaviate[source_id] = {
                                "source_id": source_id,
                                "title": work_obj.get("title") if work_obj else "Unknown",
                                "author": work_obj.get("author") if work_obj else "Unknown",
                                "chunks_count": 0,
                                "summaries_count": 0,
                                "authors": set(),
                            }
                        documents_from_weaviate[source_id]["chunks_count"] += 1

                        # Track unique authors
                        author = work_obj.get("author") if work_obj else None
                        if author:
                            documents_from_weaviate[source_id]["authors"].add(author)

            # Get summary counts
            try:
                summary_collection = client.collections.get("Summary")
                for obj in summary_collection.iterator(include_vector=False):
                    props = obj.properties
                    doc_obj = cast(Dict[str, Any], props.get("document", {}))

                    if doc_obj:
                        source_id = doc_obj.get("sourceId", "")
                        if source_id and source_id in documents_from_weaviate:
                            documents_from_weaviate[source_id]["summaries_count"] += 1
            except Exception:
                # Summary collection may not exist
                pass

    # Match with local files if they exist
    for source_id, weaviate_data in documents_from_weaviate.items():
        doc_dir: Path = output_dir / source_id
        md_file: Path = doc_dir / f"{source_id}.md"
        chunks_file: Path = doc_dir / f"{source_id}_chunks.json"
        structured_file: Path = doc_dir / f"{source_id}_structured.json"
        images_dir: Path = doc_dir / "images"

        # Load additional metadata from chunks.json if exists
        metadata: Dict[str, Any] = {}
        pages: int = 0
        toc: List[Dict[str, Any]] = []

        if chunks_file.exists():
            try:
                with open(chunks_file, "r", encoding="utf-8") as f:
                    chunks_data: Dict[str, Any] = json.load(f)
                    metadata = chunks_data.get("metadata", {})
                    pages = chunks_data.get("pages", 0)
                    toc = metadata.get("toc", [])
            except Exception:
                pass

        documents_list.append({
            "name": source_id,
            "path": str(doc_dir) if doc_dir.exists() else "",
            "has_markdown": md_file.exists(),
            "has_chunks": chunks_file.exists(),
            "has_structured": structured_file.exists(),
            "has_images": images_dir.exists() and any(images_dir.iterdir()) if images_dir.exists() else False,
            "image_count": len(list(images_dir.glob("*.png"))) if images_dir.exists() else 0,
            "metadata": metadata,
            "summaries_count": weaviate_data["summaries_count"],  # FROM WEAVIATE
            "authors_count": len(weaviate_data["authors"]),  # FROM WEAVIATE
            "chunks_count": weaviate_data["chunks_count"],  # FROM WEAVIATE
            "title": weaviate_data["title"],  # FROM WEAVIATE
            "author": weaviate_data["author"],  # FROM WEAVIATE
            "toc": toc,
        })

    return render_template("documents.html", documents=documents_list)


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Créer le dossier output si nécessaire
    app.config["UPLOAD_FOLDER"].mkdir(parents=True, exist_ok=True)
    app.run(debug=True, port=5000)

