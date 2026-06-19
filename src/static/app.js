// Local AI Assistant — Dashboard Frontend Logic

// Native IndexedDB wrapper to avoid localStorage 5MB quota exhaustion
const AppDB = {
    dbName: 'LocalAIAssistantDB',
    dbVersion: 1,
    db: null,

    init() {
        return new Promise((resolve, reject) => {
            const request = indexedDB.open(this.dbName, this.dbVersion);
            request.onerror = (e) => reject(e.target.error);
            request.onsuccess = (e) => {
                this.db = e.target.result;
                resolve();
            };
            request.onupgradeneeded = (e) => {
                const db = e.target.result;
                if (!db.objectStoreNames.contains('resume_history')) {
                    db.createObjectStore('resume_history', { keyPath: 'id' });
                }
                if (!db.objectStoreNames.contains('interview_history')) {
                    db.createObjectStore('interview_history', { keyPath: 'id' });
                }
            };
        });
    },

    save(storeName, item) {
        return new Promise((resolve, reject) => {
            if (!this.db) {
                reject(new Error('Database not initialized'));
                return;
            }
            const transaction = this.db.transaction([storeName], 'readwrite');
            const store = transaction.objectStore(storeName);
            const request = store.put(item);
            
            request.onsuccess = () => resolve();
            request.onerror = (e) => reject(e.target.error);
        });
    },

    getAll(storeName) {
        return new Promise((resolve, reject) => {
            if (!this.db) {
                reject(new Error('Database not initialized'));
                return;
            }
            const transaction = this.db.transaction([storeName], 'readonly');
            const store = transaction.objectStore(storeName);
            const request = store.getAll();
            
            request.onsuccess = () => resolve(request.result || []);
            request.onerror = (e) => reject(e.target.error);
        });
    }
};

// Global state
let activeTab = 'resume';
let availableModels = [];
let activeModel = 'llama3.2:3b';
let currentQuestionObj = null;
let currentLanguage = 'english';

const LOCALES = {
    english: {
        app_title: "Local AI Assistant",
        active_model: "Active Model:",
        select_language: "Language:",
        nav_resume: "Resume Optimizer",
        nav_interview: "Mock Interviewer",
        nav_benchmarks: "Model Benchmarks",
        nav_history: "Session History",
        sidebar_footer: "Private & secure. No data leaves your machine.",
        resume_header_title: "Resume Optimization Dashboard",
        resume_header_desc: "Analyze your resume against a target role to find skill gaps and get bulletproof re-writes.",
        resume_settings_title: "Analysis Settings",
        target_role: "Target Role",
        upload_resume: "Upload Resume PDF",
        upload_drag_drop: "Click to upload or drag & drop PDF",
        resume_plain_text: "Resume Plain Text",
        load_sample_resume: "Load Sample Resume",
        optimize_resume: "Optimize Resume",
        analyzing_resume: "Analyzing Resume...",
        querying_slm: "Querying local SLM. Structured validation loop in progress.",
        no_analysis_completed: "No Analysis Completed",
        fill_settings_resume: "Fill in the settings and click \"Optimize Resume\" to begin. The offline assistant will process the text locally.",
        match_score: "Match Score",
        candidate_name: "Candidate Name",
        est_experience: "Est. Experience",
        key_strengths: "Key Strengths",
        recommendation: "Recommendation",
        identified_skill_gaps: "Identified Skill Gaps",
        table_skill: "Skill",
        table_category: "Category",
        table_importance: "Importance",
        table_suggested_resource: "Suggested Resource",
        resume_bullet_rewrites: "Resume Bullet Point Re-writes",
        section_subtitle_rewrite: "Side-by-side suggestions to highlight achievements and quantify impact.",
        detected_format_issues: "Detected Format & Structure Issues",
        performance_metrics: "Performance Metrics (This run)",
        model_used: "Model Used:",
        retries: "Retries:",
        errors_encountered: "Errors Encountered:",
        interview_header_title: "Mock Interview Simulator",
        interview_header_desc: "Practice answering realistic behavioral and technical interview questions based on your resume.",
        interview_settings: "Interview Settings",
        interview_settings_desc: "The assistant will customize questions based on the resume loaded in the Resume Optimizer tab.",
        toggle_read_aloud: "Read Questions Aloud",
        toggle_voice_mode: "Voice Answer Mode",
        generate_question: "Generate Question",
        generating_question: "Generating Tailored Question...",
        generating_question_desc: "Model is parsing resume content to formulate a custom behavioral or technical question.",
        ready_for_interview: "Ready for Interview",
        ready_for_interview_desc: "Click \"Generate Question\" to start a custom mock interview. You can answer using the text field to receive detailed coaching feedback.",
        your_answer: "Your Answer",
        speak_answer: "Speak Answer",
        submit_answer: "Submit Answer for Feedback",
        skip_question: "Skip Question",
        realtime_coach_feedback: "Real-time AI Coach Feedback",
        streaming_placeholder: "Analyzing answer and formulating feedback...",
        interview_coaching_feedback: "Interview Coaching Feedback",
        key_strengths_bullet: "✓ Key Strengths",
        areas_to_improve: "✗ Areas to Improve",
        keyword_analysis: "Keyword Analysis",
        keyword_analysis_desc: "Evaluating coverage of core concepts recommended for this question.",
        covered_keywords: "Covered Keywords",
        missed_keywords_label: "Missed Keywords",
        suggested_framework_label: "Suggested Answer Framework (Coaching Advice)",
        try_another_question: "Try Another Question",
        history_header_title: "Session History",
        history_header_desc: "Review your past resume optimizations and mock interview practice sessions stored locally on your machine.",
        resume_history_title: "Resume Optimization History",
        no_resume_history: "No saved resume analyses yet.",
        interview_history_title: "Interview Practice History",
        no_interview_history: "No saved interview sessions yet.",
        benchmarks_header_title: "Offline SLM Inference Benchmarks",
        benchmarks_header_desc: "Compare performance metrics for 3B, 4B, and 7B parameter models benchmarked on the system's hardware.",
        model_comparison_title: "Model Comparison Summary",
        table_hdr_model: "Model",
        table_hdr_speed: "Average speed",
        table_hdr_ttft: "Avg TTFT",
        table_hdr_vram: "VRAM usage",
        table_hdr_ram: "RAM usage",
        table_hdr_compliance: "Compliance Rate",
        benchmarks_loading: "Loading benchmark data...",
        chart_tps_title: "Generation Speed (Tokens/Second)",
        chart_tps_desc: "Higher is better. Measures token production throughput.",
        chart_ttft_title: "Latency / Time-To-First-Token (TTFT)",
        chart_ttft_desc: "Lower is better. Measures response latency for cold prompts.",
        chart_mem_title: "Memory Footprint (VRAM vs RAM)",
        chart_mem_desc: "Model weights loaded in GPU VRAM vs fallback to CPU RAM.",
        chart_comp_title: "JSON Adherence Compliance Rate",
        chart_comp_desc: "Percentage of runs parsing successfully on first attempt.",
        app_footer_text: "Local AI Assistant — Pair Programming with Antigravity | CUDA Powered Offline Assistant",
        
        // Dynamic strings
        not_specified: "Not specified",
        unknown: "Unknown",
        years_label: "Years",
        no_skill_gaps: "No major skill gaps identified! Excellent match.",
        none_recommended: "None recommended",
        no_rewrites: "No rewrite suggestions generated.",
        original: "Original",
        improved_suggestion: "Improved Suggestion",
        rationale_label: "Rationale:",
        none: "None",
        all_covered: "All Covered!",
        verdict_excellent_title: "Excellent Answer!",
        verdict_excellent_desc: "Outstanding response! You demonstrated strong capability and covered most key areas.",
        verdict_good_title: "Good Effort",
        verdict_good_desc: "Solid answer, but there is room for improvement in structure and keyword coverage.",
        verdict_needs_coaching_title: "Needs Coaching",
        verdict_needs_coaching_desc: "Your answer missed critical concepts. Check the feedback below and try again.",
        toast_valid_pdf: "Please upload a valid PDF file.",
        toast_pdf_size: "PDF file size exceeds 5MB limit.",
        toast_parsing_pdf: "Parsing PDF content locally...",
        toast_pdf_parsed: "PDF resume parsed successfully.",
        toast_pdf_fail: "Failed to extract text from PDF.",
        toast_resume_length: "Please enter a valid resume text (at least 50 characters).",
        toast_target_role: "Please specify a target role.",
        toast_resume_size: "Resume text is too large (maximum 1.8MB).",
        toast_load_resume_first: "Please load or paste a resume in the Resume Optimizer tab first.",
        toast_mic_blocked: "Microphone access blocked. Enable microphone permissions.",
        toast_speech_not_supported: "Speech recognition not supported in this browser. Please use Chrome/Safari.",
        toast_detailed_answer: "Please write a more detailed answer (at least 10 characters).",
        toast_speech_start: "Microphone is active. Speak your answer.",
        toast_coaching_connect: "Connecting to AI Interview Coach...",
        loaded_resume_history: "Loaded resume analysis from history.",
        loaded_interview_history: "Loaded interview session from history.",
        candidate_label: "Candidate",
        match_label: "Match",
        score_label: "Score",
        difficulty_label: "Difficulty",
        benchmark_error: "Error querying benchmarks from local API. Make sure they have been run.",
        listening_label: "Listening... (Click to stop)",
        api_error: "API server returned error",
        fail_analyze_resume: "Failed to analyze resume after maximum retries.",
        toast_analysis_error: "Analysis Error: ",
        toast_interview_error: "Interview Error: ",
        toast_feedback_error: "Feedback Error: ",
        toast_pdf_success: "Resume PDF loaded successfully!",
        selected_label: "Selected: ",
        pdf_parsed_success_msg: "PDF Parsed successfully!",
        status_0: "Connecting to local Ollama server...",
        status_1: "Loading model weights into RAM/VRAM...",
        status_2: "Processing prompt and context...",
        status_3: "Inference in progress — generating tokens...",
        status_4: "Running Pydantic schema validation...",
        status_5: "Checking JSON compliance rules...",
        status_6: "Analyzing extracted entities...",
        status_7: "Formatting response structure...",
        target_skill: "Target Skill"
    },
    spanish: {
        app_title: "Asistente de IA Local",
        active_model: "Modelo Activo:",
        select_language: "Idioma:",
        nav_resume: "Optimizador de CV",
        nav_interview: "Simulador de Entrevista",
        nav_benchmarks: "Métricas del Modelo",
        nav_history: "Historial de Sesiones",
        sidebar_footer: "Privado y seguro. Ningún dato sale de tu máquina.",
        resume_header_title: "Tablero de Optimización de CV",
        resume_header_desc: "Analiza tu currículum frente a un puesto objetivo para encontrar brechas de habilidades y obtener redacciones optimizadas.",
        resume_settings_title: "Configuración de Análisis",
        target_role: "Puesto Objetivo",
        upload_resume: "Subir Currículum en PDF",
        upload_drag_drop: "Haz clic para subir o arrastra y suelta el PDF",
        resume_plain_text: "Texto Plano del Currículum",
        load_sample_resume: "Cargar CV de Muestra",
        optimize_resume: "Optimizar Currículum",
        analyzing_resume: "Analizando Currículum...",
        querying_slm: "Consultando el SLM local. Bucle de validación estructurado en progreso.",
        no_analysis_completed: "Ningún Análisis Completado",
        fill_settings_resume: "Completa la configuración y haz clic en \"Optimizar Currículum\" para comenzar. El asistente sin conexión procesará el texto localmente.",
        match_score: "Puntuación de Coincidencia",
        candidate_name: "Nombre del Candidato",
        est_experience: "Experiencia Estimada",
        key_strengths: "Fortalezas Clave",
        recommendation: "Recomendación",
        identified_skill_gaps: "Brechas de Habilidades Identificadas",
        table_skill: "Habilidad",
        table_category: "Categoría",
        table_importance: "Importancia",
        table_suggested_resource: "Recurso Sugerido",
        resume_bullet_rewrites: "Rediseño de Puntos Clave del Currículum",
        section_subtitle_rewrite: "Sugerencias comparativas para destacar logros y cuantificar el impacto.",
        detected_format_issues: "Problemas de Formato y Estructura Detectados",
        performance_metrics: "Métricas de Rendimiento (Esta ejecución)",
        model_used: "Modelo Utilizado:",
        retries: "Reintentos:",
        errors_encountered: "Errores Encontrados:",
        interview_header_title: "Simulador de Entrevista de Práctica",
        interview_header_desc: "Practica respondiendo preguntas de entrevista conductuales y técnicas realistas basadas en tu currículum.",
        interview_settings: "Configuración de la Entrevista",
        interview_settings_desc: "El asistente personalizará las preguntas según el currículum cargado en la pestaña del Optimizador.",
        toggle_read_aloud: "Leer Preguntas en Voz Alta",
        toggle_voice_mode: "Modo de Respuesta por Voz",
        generate_question: "Generar Pregunta",
        generating_question: "Generando Pregunta Personalizada...",
        generating_question_desc: "El modelo está analizando el contenido del currículum para formular una pregunta personalizada conductual o técnica.",
        ready_for_interview: "Listo para la Entrevista",
        ready_for_interview_desc: "Haz clic en \"Generar Pregunta\" para iniciar una entrevista simulada personalizada. Puedes responder usando el campo de texto para recibir comentarios detallados.",
        your_answer: "Tu Respuesta",
        speak_answer: "Hablar Respuesta",
        submit_answer: "Enviar Respuesta para Comentarios",
        skip_question: "Omitir Pregunta",
        realtime_coach_feedback: "Comentarios del Entrenador en Tiempo Real",
        streaming_placeholder: "Analizando la respuesta y formulando comentarios...",
        interview_coaching_feedback: "Comentarios de Preparación de la Entrevista",
        key_strengths_bullet: "✓ Fortalezas Clave",
        areas_to_improve: "✗ Áreas para Mejorar",
        keyword_analysis: "Análisis de Palabras Clave",
        keyword_analysis_desc: "Evaluando la cobertura de conceptos clave recomendados para esta pregunta.",
        covered_keywords: "Palabras Clave Cubiertas",
        missed_keywords_label: "Palabras Clave Omitidas",
        suggested_framework_label: "Marco de Respuesta Sugerido (Consejo de Preparación)",
        try_another_question: "Probar Otra Pregunta",
        history_header_title: "Historial de Sesiones",
        history_header_desc: "Revisa tus optimizaciones de currículum anteriores y sesiones de práctica de entrevistas simuladas almacenadas localmente.",
        resume_history_title: "Historial de Optimización de CV",
        no_resume_history: "Aún no hay análisis de currículum guardados.",
        interview_history_title: "Historial de Práctica de Entrevistas",
        no_interview_history: "Aún no hay sesiones de entrevista guardadas.",
        benchmarks_header_title: "Métricas de Inferencia de SLM Offline",
        benchmarks_header_desc: "Compara las métricas de rendimiento de modelos de parámetros 3B, 4B y 7B evaluados en el hardware del sistema.",
        model_comparison_title: "Resumen de Comparación de Modelos",
        table_hdr_model: "Modelo",
        table_hdr_speed: "Velocidad promedio",
        table_hdr_ttft: "TTFT promedio",
        table_hdr_vram: "Uso de VRAM",
        table_hdr_ram: "Uso de RAM",
        table_hdr_compliance: "Tasa de Cumplimiento",
        benchmarks_loading: "Cargando datos de benchmarks...",
        chart_tps_title: "Velocidad de Generación (Tokens/Segundo)",
        chart_tps_desc: "Más alto es mejor. Mide el rendimiento de producción de tokens.",
        chart_ttft_title: "Latencia / Tiempo hasta el Primer Token (TTFT)",
        chart_ttft_desc: "Más bajo es mejor. Mide la latencia de respuesta para solicitudes frías.",
        chart_mem_title: "Huella de Memoria (VRAM vs RAM)",
        chart_mem_desc: "Pesos del modelo cargados en la VRAM de la GPU frente al respaldo en la RAM de la CPU.",
        chart_comp_title: "Tasa de Cumplimiento de Adherencia JSON",
        chart_comp_desc: "Porcentaje de ejecuciones analizadas con éxito en el primer intento.",
        app_footer_text: "Asistente de IA Local — Programación en Pareja con Antigravity | Asistente Fuera de Línea con Tecnología CUDA",
        
        // Dynamic strings
        not_specified: "No especificado",
        unknown: "Desconocido",
        years_label: "Años",
        no_skill_gaps: "¡No se identificaron brechas de habilidades! Excelente coincidencia.",
        none_recommended: "Ninguno recomendado",
        no_rewrites: "No se generaron sugerencias de redacción.",
        original: "Original",
        improved_suggestion: "Sugerencia Mejorada",
        rationale_label: "Razón de ser:",
        none: "Ninguno",
        all_covered: "¡Todo Cubierto!",
        verdict_excellent_title: "¡Excelente Respuesta!",
        verdict_excellent_desc: "¡Respuesta sobresaliente! Demostraste gran capacidad y cubriste la mayoría de las áreas clave.",
        verdict_good_title: "Buen Esfuerzo",
        verdict_good_desc: "Respuesta sólida, pero hay margen de mejora en la estructura y cobertura de palabras clave.",
        verdict_needs_coaching_title: "Necesita Preparación",
        verdict_needs_coaching_desc: "Tu respuesta omitió conceptos críticos. Revisa los comentarios de abajo e inténtalo de nuevo.",
        toast_valid_pdf: "Por favor, sube un archivo PDF válido.",
        toast_pdf_size: "El tamaño del archivo PDF supera el límite de 5 MB.",
        toast_parsing_pdf: "Analizando el contenido del PDF localmente...",
        toast_pdf_parsed: "Currículum PDF analizado con éxito.",
        toast_pdf_fail: "No se pudo extraer texto del PDF.",
        toast_resume_length: "Por favor, introduce un texto de currículum válido (al menos 50 caracteres).",
        toast_target_role: "Por favor, especifica un puesto objetivo.",
        toast_resume_size: "El texto del currículum es demasiado grande (máximo 1,8 MB).",
        toast_load_resume_first: "Por favor, primero carga o pega un currículum en la pestaña del Optimizador de CV.",
        toast_mic_blocked: "Acceso al micrófono bloqueado. Habilita los permisos del micrófono.",
        toast_speech_not_supported: "El reconocimiento de voz no es compatible con este navegador. Por favor, usa Chrome/Safari.",
        toast_detailed_answer: "Por favor, escribe una respuesta más detallada (al menos 10 caracteres).",
        toast_speech_start: "El micrófono está activo. Di tu respuesta.",
        toast_coaching_connect: "Conectando con el preparador de entrevistas de IA...",
        loaded_resume_history: "Se cargó el análisis del currículum desde el historial.",
        loaded_interview_history: "Se cargó la sesión de entrevista desde el historial.",
        candidate_label: "Candidato",
        match_label: "Coincidencia",
        score_label: "Puntuación",
        difficulty_label: "Dificultad",
        benchmark_error: "Error al consultar los benchmarks desde la API local. Asegúrese de que se hayan ejecutado.",
        listening_label: "Escuchando... (Haz clic para detener)",
        api_error: "El servidor API devolvió un error",
        fail_analyze_resume: "No se pudo analizar el currículum después del número máximo de reintentos.",
        toast_analysis_error: "Error de análisis: ",
        toast_interview_error: "Error de entrevista: ",
        toast_feedback_error: "Error de comentarios: ",
        toast_pdf_success: "¡Currículum en PDF cargado con éxito!",
        selected_label: "Seleccionado: ",
        pdf_parsed_success_msg: "¡PDF analizado con éxito!",
        status_0: "Conectando al servidor local de Ollama...",
        status_1: "Cargando los pesos del modelo en RAM/VRAM...",
        status_2: "Procesando la solicitud y el contexto...",
        status_3: "Inferencia en progreso — generando tokens...",
        status_4: "Ejecutando la validación del esquema Pydantic...",
        status_5: "Verificando las reglas de cumplimiento de JSON...",
        status_6: "Analizando las entidades extraídas...",
        status_7: "Formateando la estructura de la respuesta...",
        target_skill: "Habilidad Objetivo"
    },
    german: {
        app_title: "Lokaler KI-Assistent",
        active_model: "Aktives Modell:",
        select_language: "Sprache:",
        nav_resume: "Lebenslauf-Optimierer",
        nav_interview: "Mock-Interviewer",
        nav_benchmarks: "Modell-Benchmarks",
        nav_history: "Sitzungsverlauf",
        sidebar_footer: "Privat & sicher. Keine Daten verlassen Ihren Rechner.",
        resume_header_title: "Dashboard zur Lebenslaufoptimierung",
        resume_header_desc: "Analysieren Sie Ihren Lebenslauf für eine Zielrolle, um Qualifikationslücken zu finden und professionelle Umschreibungen zu erhalten.",
        resume_settings_title: "Analyseeinstellungen",
        target_role: "Target Role",
        upload_resume: "Lebenslauf-PDF hochladen",
        upload_drag_drop: "Klicken Sie zum Hochladen oder ziehen Sie das PDF hierher",
        resume_plain_text: "Lebenslauf als Klartext",
        load_sample_resume: "Muster-Lebenslauf laden",
        optimize_resume: "Lebenslauf optimieren",
        analyzing_resume: "Lebenslauf wird analysiert...",
        querying_slm: "Lokales SLM wird abgefragt. Strukturierte Validierungsschleife läuft.",
        no_analysis_completed: "Keine Analyse durchgeführt",
        fill_settings_resume: "Füllen Sie die Einstellungen aus und klicken Sie auf „Lebenslauf optimieren“, um zu beginnen. Der Offline-Assistent verarbeitet den Text lokal.",
        match_score: "Übereinstimmung",
        candidate_name: "Name des Kandidaten",
        est_experience: "Geschätzte Erfahrung",
        key_strengths: "Schlüsselstärken",
        recommendation: "Empfehlung",
        identified_skill_gaps: "Identifizierte Qualifikationslücken",
        table_skill: "Fähigkeit",
        table_category: "Kategorie",
        table_importance: "Wichtigkeit",
        table_suggested_resource: "Empfohlene Ressource",
        resume_bullet_rewrites: "Umschreibungen von Lebenslaufpunkten",
        section_subtitle_rewrite: "Gegenüberstellung von Vorschlägen zur Hervorhebung von Erfolgen und Quantifizierung der Wirkung.",
        detected_format_issues: "Erkannte Format- und Strukturprobleme",
        performance_metrics: "Leistungsmetriken (Dieser Durchlauf)",
        model_used: "Verwendetes Modell:",
        retries: "Wiederholungen:",
        errors_encountered: "Aufgetretene Fehler:",
        interview_header_title: "Mock-Interview-Simulator",
        interview_header_desc: "Üben Sie das Beantworten realistischer verhaltensbezogener und technischer Interviewfragen basierend auf Ihrem Lebenslauf.",
        interview_settings: "Interview-Einstellungen",
        interview_settings_desc: "Der Assistent passt die Fragen basierend auf dem im Lebenslauf-Optimierer geladenen Lebenslauf an.",
        toggle_read_aloud: "Fragen laut vorlesen",
        toggle_voice_mode: "Sprachantwortmodus",
        generate_question: "Frage generieren",
        generating_question: "Maßgeschneiderte Frage wird generiert...",
        generating_question_desc: "Modell analysiert den Lebenslaufinhalt, um eine benutzerdefinierte verhaltensbezogene oder technische Frage zu formulieren.",
        ready_for_interview: "Bereit für das Interview",
        ready_for_interview_desc: "Klicken Sie auf „Frage generieren“, um ein individuelles Interview zu starten. Antworten Sie im Textfeld, um detailliertes Coaching-Feedback zu erhalten.",
        your_answer: "Ihre Antwort",
        speak_answer: "Antwort einsprechen",
        submit_answer: "Antwort zur Auswertung einreichen",
        skip_question: "Frage überspringen",
        realtime_coach_feedback: "Echtzeit-KI-Coach-Feedback",
        streaming_placeholder: "Antwort wird analysiert und Feedback formuliert...",
        interview_coaching_feedback: "Interview-Coaching-Feedback",
        key_strengths_bullet: "✓ Hauptstärken",
        areas_to_improve: "✗ Verbesserungsbereiche",
        keyword_analysis: "Schlüsselwortanalyse",
        keyword_analysis_desc: "Bewertung der Abdeckung der für diese Frage empfohlenen Kernkonzepte.",
        covered_keywords: "Abgedeckte Schlüsselwörter",
        missed_keywords_label: "Fehlende Schlüsselwörter",
        suggested_framework_label: "Empfohlenes Antwortgerüst (Coaching-Hinweis)",
        try_another_question: "Nächste Frage versuchen",
        history_header_title: "Sitzungsverlauf",
        history_header_desc: "Überprüfen Sie Ihre vergangenen Lebenslaufoptimierungen und Interview-Übungsstunden, die lokal auf Ihrem Rechner gespeichert sind.",
        resume_history_title: "Lebenslaufoptimierungsverlauf",
        no_resume_history: "Noch keine Lebenslaufanalysen gespeichert.",
        interview_history_title: "Interview-Übungsverlauf",
        no_interview_history: "Noch keine Interviewsitzungen gespeichert.",
        benchmarks_header_title: "Offline-SLM-Inferenz-Benchmarks",
        benchmarks_header_desc: "Vergleichen Sie Leistungskennzahlen für Modelle mit 3B, 4B und 7B Parametern, die auf der Systemhardware getestet wurden.",
        model_comparison_title: "Modellvergleichsübersicht",
        table_hdr_model: "Modell",
        table_hdr_speed: "Average speed",
        table_hdr_ttft: "Avg TTFT",
        table_hdr_vram: "VRAM-Nutzung",
        table_hdr_ram: "RAM-Nutzung",
        table_hdr_compliance: "JSON-Konformitätsrate",
        benchmarks_loading: "Benchmark-Daten werden geladen...",
        chart_tps_title: "Generierungsgeschwindigkeit (Tokens/Sekunde)",
        chart_tps_desc: "Höher ist besser. Misst den Durchsatz der Token-Produktion.",
        chart_ttft_title: "Latenz / Zeit bis zum ersten Token (TTFT)",
        chart_ttft_desc: "Niedriger ist besser. Misst die Antwortlatenz bei kalten Prompts.",
        chart_mem_title: "Speicherplatzbedarf (VRAM vs. RAM)",
        chart_mem_desc: "Modellgewichte geladen im GPU-VRAM im Vergleich zum CPU-RAM-Fallback.",
        chart_comp_title: "JSON-Einhaltungsrate",
        chart_comp_desc: "Prozentsatz der Durchläufe, die beim ersten Versuch erfolgreich geparst wurden.",
        app_footer_text: "Lokaler KI-Assistent — Pair Programming mit Antigravity | CUDA-gestützter Offline-Assistent",
        
        // Dynamic strings
        not_specified: "Nicht angegeben",
        unknown: "Unbekannt",
        years_label: "Jahre",
        no_skill_gaps: "Keine wesentlichen Qualifikationslücken festgestellt! Hervorragende Übereinstimmung.",
        none_recommended: "Keine empfohlen",
        no_rewrites: "Keine Formulierungsvorschläge generiert.",
        original: "Original",
        improved_suggestion: "Verbesserter Vorschlag",
        rationale_label: "Begründung:",
        none: "Keine",
        all_covered: "Alles abgedeckt!",
        verdict_excellent_title: "Hervorragende Antwort!",
        verdict_excellent_desc: "Herausragende Antwort! Sie haben starke Fähigkeiten bewiesen und die meisten Kernbereiche abgedeckt.",
        verdict_good_title: "Gute Leistung",
        verdict_good_desc: "Solide Antwort, aber es gibt noch Raum für Verbesserungen bei der Struktur und Schlüsselwortabdeckung.",
        verdict_needs_coaching_title: "Coaching empfohlen",
        verdict_needs_coaching_desc: "Ihre Antwort hat wichtige Konzepte ausgelassen. Überprüfen Sie das Feedback unten und versuchen Sie es erneut.",
        toast_valid_pdf: "Bitte laden Sie eine gültige PDF-Datei hoch.",
        toast_pdf_size: "Die PDF-Dateigröße überschreitet das Limit von 5 MB.",
        toast_parsing_pdf: "PDF-Inhalt wird lokal analysiert...",
        toast_pdf_parsed: "PDF-Lebenslauf erfolgreich analysiert.",
        toast_pdf_fail: "Text konnte nicht aus der PDF-Datei extrahiert werden.",
        toast_resume_length: "Bitte geben Sie einen gültigen Lebenslauftext ein (mindestens 50 Zeichen).",
        toast_target_role: "Bitte geben Sie eine Zielrolle an.",
        toast_resume_size: "Der Lebenslauftext ist zu groß (maximal 1,8 MB).",
        toast_load_resume_first: "Bitte laden oder fügen Sie zuerst einen Lebenslauf auf der Registerkarte Lebenslauf-Optimierer ein.",
        toast_mic_blocked: "Mikrofonzugriff blockiert. Aktivieren Sie die Mikrofonberechtigungen.",
        toast_speech_not_supported: "Spracherkennung wird in diesem Browser nicht unterstützt. Bitte verwenden Sie Chrome/Safari.",
        toast_detailed_answer: "Bitte schreiben Sie eine detailliertere Antwort (mindestens 10 Zeichen).",
        toast_speech_start: "Mikrofon ist aktiv. Sprechen Sie Ihre Antwort.",
        toast_coaching_connect: "Verbindung mit dem KI-Interview-Coach wird hergestellt...",
        loaded_resume_history: "Lebenslaufanalyse aus dem Verlauf geladen.",
        loaded_interview_history: "Interview-Sitzung aus dem Verlauf geladen.",
        candidate_label: "Kandidat",
        match_label: "Übereinstimmung",
        score_label: "Bewertung",
        difficulty_label: "Schwierigkeit",
        benchmark_error: "Fehler beim Abfragen der Benchmarks von der lokalen API. Stellen Sie sicher, dass sie ausgeführt wurden.",
        listening_label: "Zuhören... (Klicken zum Stoppen)",
        api_error: "API-Server hat einen Fehler zurückgegeben",
        fail_analyze_resume: "Lebenslauf konnte nach maximalen Versuchen nicht analysiert werden.",
        toast_analysis_error: "Analysefehler: ",
        toast_interview_error: "Interview-Fehler: ",
        toast_feedback_error: "Feedback-Fehler: ",
        toast_pdf_success: "Lebenslauf-PDF erfolgreich geladen!",
        selected_label: "Ausgewählt: ",
        pdf_parsed_success_msg: "PDF erfolgreich analysiert!",
        status_0: "Verbindung zum lokalen Ollama-Server wird hergestellt...",
        status_1: "Modellgewichte werden in RAM/VRAM geladen...",
        status_2: "Prompt und Kontext werden verarbeitet...",
        status_3: "Inferenz läuft — Tokens werden generiert...",
        status_4: "Pydantic-Schema-Validierung wird ausgeführt...",
        status_5: "JSON-Konformitätsregeln werden überprüft...",
        status_6: "Extrahierte Entitäten werden analysiert...",
        status_7: "Antwortstruktur wird formatiert...",
        target_skill: "Ziel-Kompetenz"
    }
};

function t(key) {
    if (LOCALES[currentLanguage] && LOCALES[currentLanguage][key]) {
        return LOCALES[currentLanguage][key];
    }
    if (LOCALES['english'] && LOCALES['english'][key]) {
        return LOCALES['english'][key];
    }
    return key;
}

function changeLanguage(lang) {
    currentLanguage = lang;
    console.log(`Language changed to: ${currentLanguage}`);
    translatePage(currentLanguage);
    
    if (speechRecognition) {
        if (isRecognizing) {
            speechRecognition.stop();
        }
        let langCode = 'en-US';
        if (currentLanguage === 'spanish') langCode = 'es-ES';
        else if (currentLanguage === 'german') langCode = 'de-DE';
        speechRecognition.lang = langCode;
    }
}

function translatePage(lang) {
    const elements = document.querySelectorAll('[data-i18n]');
    elements.forEach(el => {
        const key = el.getAttribute('data-i18n');
        if (LOCALES[lang] && LOCALES[lang][key]) {
            if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
                if (el.placeholder !== undefined) {
                    el.placeholder = LOCALES[lang][key];
                }
            } else {
                el.textContent = LOCALES[lang][key];
            }
        }
    });
}


// Toast notification system
function showToast(message, type = 'error', duration = 5000) {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);

    requestAnimationFrame(() => {
        toast.classList.add('show');
    });

    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

// Predefined sample resume for testing
const SAMPLE_RESUME = `Jane Miller
jane.miller@email.com | (555) 987-6543 | LinkedIn: linkedin.com/in/janemiller

SUMMARY
Dynamic Software Engineer with over 4 years of experience specializing in backend system design, RESTful APIs, and cloud-native application deployment. Strong proficiency in Python, PostgreSQL, and AWS, with a growing focus on Docker and DevOps processes.

EXPERIENCE
Software Engineer II, GlobalTech Solutions (2022 - Present)
- Designed and built RESTful APIs using FastAPI and Django, reducing API response times by 35% through query optimization and Redis caching.
- Maintained PostgreSQL databases, writing complex SQL queries and migrations.
- Contributed to migrating local services to AWS (EC2, S3, RDS).
- Participated in weekly code reviews and agile sprint planning sessions.

Junior Backend Developer, AppFactory Corp (2020 - 2022)
- Worked on a Python/Flask codebase to build data processing utilities.
- Wrote unit and integration tests using pytest, raising test coverage from 65% to 80%.
- Assisted senior engineers in debugging production databases.

EDUCATION
B.S. in Computer Science, Tech Institute (2016 - 2020)
GPA: 3.6/4.0

SKILLS
Languages: Python, JavaScript, SQL, HTML/CSS
Frameworks: FastAPI, Django, Flask, Express.js
Databases: PostgreSQL, Redis, SQLite
Tools: Git, AWS (EC2, S3), pytest, Postman, Linux`;

// Initialize application on load
window.addEventListener('DOMContentLoaded', async () => {
    try {
        await AppDB.init();
        console.log('AppDB initialized successfully.');
    } catch (e) {
        console.error('Failed to initialize AppDB:', e);
    }
    checkOllamaHealth();
    // Periodically poll health every 15 seconds
    setInterval(checkOllamaHealth, 15000);
    
    // Set up model selector change listener
    const modelSelect = document.getElementById('global-model-select');
    modelSelect.addEventListener('change', (e) => {
        activeModel = e.target.value;
        console.log(`Active model changed to: ${activeModel}`);
    });
    
    // Automatically load benchmarks on tab switch
    const navBtnBenchmarks = document.getElementById('nav-btn-benchmarks');
    navBtnBenchmarks.addEventListener('click', loadBenchmarkData);
});

// Health check with Ollama & Gemini backend
async function checkOllamaHealth() {
    const statusDot = document.getElementById('status-dot');
    const statusText = document.getElementById('status-text');
    const modelSelect = document.getElementById('global-model-select');
    
    try {
        const response = await fetch('/health');
        if (!response.ok) throw new Error('Status not OK');
        
        const data = await response.json();
        
        statusDot.className = 'status-dot-pulse online';
        statusText.textContent = 'Ollama/Gemini Online';
        
        // Hide warning banners if visible
        document.getElementById('ollama-warning-resume').classList.add('hidden');
        document.getElementById('ollama-warning-interview').classList.add('hidden');
        
        // Enable action buttons
        document.getElementById('btn-analyze-resume').disabled = false;
        document.getElementById('btn-start-interview').disabled = false;
        
        // Populate model selector if models are returned
        if (data.models_available && data.models_available.length > 0) {
            availableModels = data.models_available;
            
            // Clear current options and rebuild
            const previousVal = modelSelect.value;
            modelSelect.innerHTML = '';
            availableModels.forEach(model => {
                const opt = document.createElement('option');
                opt.value = model;
                opt.textContent = formatModelName(model);
                modelSelect.appendChild(opt);
            });
            
            if (previousVal && availableModels.includes(previousVal)) {
                modelSelect.value = previousVal;
                activeModel = previousVal;
            } else if (availableModels.includes('gemini-2.5-flash')) {
                modelSelect.value = 'gemini-2.5-flash';
                activeModel = 'gemini-2.5-flash';
            } else if (availableModels.includes('llama3.2:3b') || availableModels.includes('llama3.2')) {
                const defaultLlama = availableModels.find(m => m === 'llama3.2:3b' || m.startsWith('llama3.2'));
                modelSelect.value = defaultLlama;
                activeModel = defaultLlama;
            } else if (availableModels.length > 0) {
                activeModel = availableModels[0];
            }
        }
    } catch (error) {
        console.error('API health check failed:', error);
        statusDot.className = 'status-dot-pulse offline';
        statusText.textContent = 'Assistant Offline';
        
        // Show warning banners
        document.getElementById('ollama-warning-resume').classList.remove('hidden');
        document.getElementById('ollama-warning-interview').classList.remove('hidden');
        
        // Disable action buttons
        document.getElementById('btn-analyze-resume').disabled = true;
        document.getElementById('btn-start-interview').disabled = true;
    }
}

function formatModelName(model) {
    if (model.startsWith('gemini-')) {
        return 'Google Gemini ' + model.replace('gemini-', '').toUpperCase();
    }
    if (model.includes(':')) {
        const parts = model.split(':');
        return `${parts[0].charAt(0).toUpperCase() + parts[0].slice(1)} (${parts[1]})`;
    }
    return model.charAt(0).toUpperCase() + model.slice(1);
}

// Switch tabs in sidebar
function switchTab(tabName) {
    activeTab = tabName;
    
    // Stop speaking when switching tabs
    window.speechSynthesis.cancel();
    
    // Update nav buttons
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    document.getElementById(`nav-btn-${tabName}`).classList.add('active');
    
    // Update panes
    document.querySelectorAll('.tab-pane').forEach(pane => {
        pane.classList.remove('active');
    });
    document.getElementById(`tab-${tabName}`).classList.add('active');
    
    if (tabName === 'history') {
        renderHistory();
    }
}

// Load sample resume
function loadSampleResume() {
    document.getElementById('resume-text').value = SAMPLE_RESUME;
}

// PDF.js Client-Side PDF Upload Parser
async function handlePDFUpload(event) {
    const file = event.target.files[0];
    if (!file) return;

    if (file.type !== 'application/pdf') {
        showToast(t('toast_valid_pdf'), 'warning');
        return;
    }

    // Limit PDF size to 5MB to avoid browser freeze
    const maxPdfSize = 5 * 1024 * 1024;
    if (file.size > maxPdfSize) {
        showToast(t('toast_pdf_size'), 'warning');
        return;
    }

    const filenameLabel = document.getElementById('pdf-filename');
    const uploadText = document.querySelector('#pdf-upload-zone .upload-text');
    
    filenameLabel.textContent = `${t('selected_label')}${file.name}`;
    uploadText.textContent = t('toast_parsing_pdf');

    const reader = new FileReader();
    reader.onload = async function() {
        try {
            const typedArray = new Uint8Array(this.result);
            
            // Set up worker source
            pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
            
            const pdf = await pdfjsLib.getDocument({ data: typedArray }).promise;
            let extractedText = '';
            
            for (let i = 1; i <= pdf.numPages; i++) {
                const page = await pdf.getPage(i);
                const textContent = await page.getTextContent();
                const pageText = textContent.items.map(item => item.str).join(' ');
                extractedText += pageText + '\n';
            }

            if (extractedText.trim().length < 50) {
                throw new Error('PDF contains too little text or might be scanned.');
            }

            document.getElementById('resume-text').value = extractedText.trim();
            uploadText.textContent = t('pdf_parsed_success_msg');
            showToast(t('toast_pdf_success'), 'success');
        } catch (error) {
            console.error('PDF parse error:', error);
            uploadText.textContent = t('toast_pdf_fail');
            showToast(t('toast_pdf_fail'), 'error');
            filenameLabel.textContent = '';
        }
    };
    reader.readAsArrayBuffer(file);
}

// Micro-status updates during long-running generation
function animateStatus(type, fillElementId, statusTextId, durationMs) {
    const statuses = [
        t('status_0'),
        t('status_1'),
        t('status_2'),
        t('status_3'),
        t('status_4'),
        t('status_5'),
        t('status_6'),
        t('status_7')
    ];
    
    const fillEl = document.getElementById(fillElementId);
    const statusEl = document.getElementById(statusTextId);
    if (!fillEl || !statusEl) return null;
    
    let currentIdx = 0;
    statusEl.textContent = statuses[0];
    fillEl.style.width = '5%';
    
    const interval = setInterval(() => {
        currentIdx = (currentIdx + 1) % statuses.length;
        statusEl.textContent = statuses[currentIdx];
        
        // Progressively increment fill percentage (but cap below 100%)
        let currentWidth = parseFloat(fillEl.style.width);
        if (currentWidth < 92) {
            fillEl.style.width = `${currentWidth + 7}%`;
        }
    }, durationMs / 10);
    
    return interval;
}

// RESUME ANALYSIS
async function triggerResumeAnalysis() {
    const resumeText = document.getElementById('resume-text').value.trim();
    const targetRole = document.getElementById('resume-target-role').value.trim();
    
    if (!resumeText || resumeText.length < 50) {
        showToast(t('toast_resume_length'), 'warning');
        return;
    }
    if (!targetRole) {
        showToast(t('toast_target_role'), 'warning');
        return;
    }
    
    // Check if the resume text length exceeds the size limit to avoid 413 backend errors
    if (resumeText.length > 1.8 * 1024 * 1024) {
        showToast(t('toast_resume_size'), 'warning');
        return;
    }
    
    // Update UI elements to loading state
    const btn = document.getElementById('btn-analyze-resume');
    btn.disabled = true;
    btn.querySelector('.spinner').classList.remove('hidden');
    
    const loadingCard = document.getElementById('resume-loading');
    const emptyCard = document.getElementById('resume-empty-state');
    const resultsWrapper = document.getElementById('resume-results');
    
    loadingCard.classList.remove('hidden');
    emptyCard.classList.add('hidden');
    resultsWrapper.classList.add('hidden');
    
    // Start mock progress loading animations
    const loadDuration = activeModel.startsWith('gemini-') ? 4000 : 20000;
    const animInterval = animateStatus('resume', 'resume-progress-fill', 'resume-micro-status', loadDuration);
    
    try {
        const response = await fetch('/analyze-resume', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                resume_text: resumeText,
                target_role: targetRole,
                model: activeModel,
                language: currentLanguage
            })
        });
        
        clearInterval(animInterval);
        
        if (!response.ok) {
            if (response.status === 413) {
                throw new Error(t('toast_resume_size'));
            }
            throw new Error(t('api_error'));
        }
        const result = await response.json();
        
        if (!result.success || !result.data) {
            let errorMsg = result.errors && result.errors.length > 0 
                ? result.errors.join('<br>') 
                : t('fail_analyze_resume');
            throw new Error(errorMsg);
        }
        
        renderResumeResults(result);
        
        // Save to LocalStorage History
        saveResumeHistory(resumeText, targetRole, activeModel, result.data);
        
    } catch (error) {
        console.error('Resume optimization error:', error);
        clearInterval(animInterval);
        showToast(t('toast_analysis_error') + error.message, 'error', 8000);
        emptyCard.classList.remove('hidden');
    } finally {
        btn.disabled = false;
        btn.querySelector('.spinner').classList.add('hidden');
        loadingCard.classList.add('hidden');
    }
}

// Render analyzed resume results
function renderResumeResults(res) {
    const data = res.data;
    
    // Update candidate details
    document.getElementById('res-candidate-name').textContent = data.candidate_name || t('not_specified');
    document.getElementById('res-experience').textContent = data.years_experience !== null ? `${data.years_experience} ${t('years_label')}` : t('unknown');
    
    // Update overall recommendation
    document.getElementById('res-recommendation').textContent = data.overall_recommendation;
    
    // Score circle animation
    const score = Math.round(data.skill_analysis.matching_score);
    const circle = document.getElementById('score-circle');
    const text = document.getElementById('score-text');
    circle.style.strokeDasharray = `${score}, 100`;
    text.textContent = `${score}%`;
    
    // Render strengths
    const strengthsUl = document.getElementById('res-strengths');
    strengthsUl.innerHTML = '';
    data.skill_analysis.strengths.forEach(str => {
        const li = document.createElement('li');
        li.textContent = str;
        strengthsUl.appendChild(li);
    });
    
    // Render skill gaps
    const gapsTbody = document.getElementById('res-skill-gaps');
    gapsTbody.innerHTML = '';
    if (data.skill_analysis.missing_skills.length === 0) {
        gapsTbody.innerHTML = `<tr><td colspan="4" style="text-align:center;">${t('no_skill_gaps')}</td></tr>`;
    } else {
        data.skill_analysis.missing_skills.forEach(gap => {
            const tr = document.createElement('tr');
            
            const tdName = document.createElement('td');
            tdName.innerHTML = `<strong>${gap.skill_name}</strong>`;
            
            const tdCat = document.createElement('td');
            tdCat.innerHTML = `<span class="badge" style="background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1);">${gap.category}</span>`;
            
            const tdImportance = document.createElement('td');
            tdImportance.textContent = gap.importance;
            
            const tdResource = document.createElement('td');
            tdResource.textContent = gap.suggested_resource || t('none_recommended');
            
            tr.appendChild(tdName);
            tr.appendChild(tdCat);
            tr.appendChild(tdImportance);
            tr.appendChild(tdResource);
            
            gapsTbody.appendChild(tr);
        });
    }
    
    // Render bullet re-writes
    const rewritesContainer = document.getElementById('res-bullet-rewrites');
    rewritesContainer.innerHTML = '';
    if (data.skill_analysis.bullet_point_improvements.length === 0) {
        rewritesContainer.innerHTML = `<p class="text-muted">${t('no_rewrites')}</p>`;
    } else {
        data.skill_analysis.bullet_point_improvements.forEach(rewrite => {
            const card = document.createElement('div');
            card.className = 'rewrite-card';

            const split = document.createElement('div');
            split.className = 'rewrite-split';

            const origBox = document.createElement('div');
            origBox.className = 'orig-box';
            const origH = document.createElement('h5');
            origH.textContent = t('original');
            const origP = document.createElement('p');
            origP.textContent = rewrite.original;
            origBox.appendChild(origH);
            origBox.appendChild(origP);

            const imprBox = document.createElement('div');
            imprBox.className = 'impr-box';
            const imprH = document.createElement('h5');
            imprH.textContent = t('improved_suggestion');
            const imprP = document.createElement('p');
            imprP.textContent = rewrite.improved;
            imprBox.appendChild(imprH);
            imprBox.appendChild(imprP);

            split.appendChild(origBox);
            split.appendChild(imprBox);

            const rationaleDiv = document.createElement('div');
            rationaleDiv.className = 'rewrite-rationale';
            const rationaleLabel = document.createElement('strong');
            rationaleLabel.textContent = t('rationale_label') + ' ';
            const rationaleText = document.createTextNode(rewrite.rationale);
            rationaleDiv.appendChild(rationaleLabel);
            rationaleDiv.appendChild(rationaleText);

            card.appendChild(split);
            card.appendChild(rationaleDiv);
            rewritesContainer.appendChild(card);
        });
    }
    
    // Format issues
    const formatCard = document.getElementById('format-issues-card');
    const formatUl = document.getElementById('res-format-issues');
    formatUl.innerHTML = '';
    if (data.format_issues && data.format_issues.length > 0) {
        formatCard.classList.remove('hidden');
        data.format_issues.forEach(issue => {
            const li = document.createElement('li');
            li.textContent = issue;
            formatUl.appendChild(li);
        });
    } else {
        formatCard.classList.add('hidden');
    }
    
    // Performance stats
    document.getElementById('perf-model').textContent = res.model;
    document.getElementById('perf-attempts').textContent = `${res.attempts}`;
    document.getElementById('perf-errors').textContent = res.errors && res.errors.length > 0 ? res.errors.join(' | ') : t('none');
    
    // Reveal results wrapper
    document.getElementById('resume-results').classList.remove('hidden');
}

// Speech Synthesis & Recognition Integration
let currentSpeechUtterance = null;

function speakText(text) {
    const readAloudEnabled = document.getElementById('toggle-read-aloud').checked;
    if (!readAloudEnabled) return;

    window.speechSynthesis.cancel();

    // Remove markdown symbols for clear pronunciation
    const cleanText = text.replace(/[*#_`~=]/g, '').trim();

    currentSpeechUtterance = new SpeechSynthesisUtterance(cleanText);
    
    const voices = window.speechSynthesis.getVoices();
    let langPrefix = 'en';
    if (currentLanguage === 'spanish') langPrefix = 'es';
    else if (currentLanguage === 'german') langPrefix = 'de';

    const langVoice = voices.find(voice => voice.lang.startsWith(langPrefix) && voice.localService) || voices.find(voice => voice.lang.startsWith(langPrefix));
    if (langVoice) {
        currentSpeechUtterance.voice = langVoice;
    }

    window.speechSynthesis.speak(currentSpeechUtterance);
}

// Speech Recognition (Speech-to-Text)
let speechRecognition = null;
let isRecognizing = false;

function initSpeechRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        console.warn('Speech Recognition API not supported in this browser.');
        return null;
    }

    const rec = new SpeechRecognition();
    rec.continuous = true;
    rec.interimResults = true;
    
    let langCode = 'en-US';
    if (currentLanguage === 'spanish') langCode = 'es-ES';
    else if (currentLanguage === 'german') langCode = 'de-DE';
    rec.lang = langCode;

    rec.onstart = () => {
        isRecognizing = true;
        const micBtn = document.getElementById('btn-mic');
        const micText = document.getElementById('mic-text');
        micBtn.classList.add('recording');
        micText.textContent = t('listening_label');
    };

    rec.onresult = (event) => {
        let finalTranscript = '';
        for (let i = event.resultIndex; i < event.results.length; ++i) {
            if (event.results[i].isFinal) {
                finalTranscript += event.results[i][0].transcript + ' ';
            }
        }
        if (finalTranscript) {
            const textarea = document.getElementById('interview-answer');
            textarea.value += finalTranscript;
        }
    };

    rec.onerror = (event) => {
        console.error('Speech recognition error:', event.error);
        if (event.error === 'not-allowed') {
            showToast(t('toast_mic_blocked'), 'warning');
        }
    };

    rec.onend = () => {
        isRecognizing = false;
        const micBtn = document.getElementById('btn-mic');
        const micText = document.getElementById('mic-text');
        micBtn.classList.remove('recording');
        micText.textContent = t('speak_answer');
    };

    return rec;
}

function toggleSpeechRecognition() {
    if (!speechRecognition) {
        speechRecognition = initSpeechRecognition();
    }
    if (!speechRecognition) {
        showToast(t('toast_speech_not_supported'), 'warning');
        return;
    }

    if (isRecognizing) {
        speechRecognition.stop();
    } else {
        let langCode = 'en-US';
        if (currentLanguage === 'spanish') langCode = 'es-ES';
        else if (currentLanguage === 'german') langCode = 'de-DE';
        speechRecognition.lang = langCode;
        speechRecognition.start();
    }
}

function toggleVoiceModeUI(enabled) {
    const micBtn = document.getElementById('btn-mic');
    if (enabled) {
        micBtn.classList.remove('hidden');
    } else {
        micBtn.classList.add('hidden');
        if (isRecognizing && speechRecognition) {
            speechRecognition.stop();
        }
    }
}

// MOCK INTERVIEW SIMULATOR
async function startInterview() {
    const resumeText = document.getElementById('resume-text').value.trim();
    const targetRole = document.getElementById('interview-target-role').value.trim();
    
    // Stop any speaking audio
    window.speechSynthesis.cancel();
    
    if (!resumeText || resumeText.length < 50) {
        showToast(t('toast_load_resume_first'), 'warning');
        return;
    }
    if (!targetRole) {
        showToast(t('toast_target_role'), 'warning');
        return;
    }
    
    // Toggle loading UI
    const btn = document.getElementById('btn-start-interview');
    btn.disabled = true;
    btn.querySelector('.spinner').classList.remove('hidden');
    
    const loadingCard = document.getElementById('interview-loading');
    const emptyCard = document.getElementById('interview-empty-state');
    const activeBox = document.getElementById('interview-active-question');
    const feedbackView = document.getElementById('interview-feedback-view');
    const streamingView = document.getElementById('interview-streaming-view');
    
    loadingCard.classList.remove('hidden');
    emptyCard.classList.add('hidden');
    activeBox.classList.add('hidden');
    feedbackView.classList.add('hidden');
    streamingView.classList.add('hidden');
    
    try {
        const response = await fetch('/interview/generate-questions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                resume_text: resumeText,
                target_role: targetRole,
                model: activeModel,
                language: currentLanguage
            })
        });
        
        if (!response.ok) throw new Error('API returned an error');
        const result = await response.json();
        
        if (!result.success || !result.data) {
            throw new Error(result.errors && result.errors.length > 0 ? result.errors[0] : t('fail_generate_question'));
        }
        
        currentQuestionObj = result.data;
        
        // Populate UI
        document.getElementById('int-question-text').textContent = currentQuestionObj.question;
        document.getElementById('int-difficulty').textContent = currentQuestionObj.difficulty.toUpperCase();
        document.getElementById('int-type').textContent = currentQuestionObj.question_type.toUpperCase();
        document.getElementById('int-skill').textContent = `${t('target_skill')}: ${currentQuestionObj.target_skill}`;
        
        // Clear text field
        document.getElementById('interview-answer').value = '';
        
        // Reveal Question panel
        activeBox.classList.remove('hidden');
        
        // Speak question if enabled
        speakText("Question: " + currentQuestionObj.question);
        
    } catch (error) {
        console.error('Interview question generation error:', error);
        showToast(t('toast_interview_error') + error.message, 'error', 8000);
        emptyCard.classList.remove('hidden');
    } finally {
        btn.disabled = false;
        btn.querySelector('.spinner').classList.add('hidden');
        loadingCard.classList.add('hidden');
    }
}

// REAL-TIME STREAMING INTERVIEW ANSWER SUBMISSION
async function submitInterviewAnswer() {
    const answer = document.getElementById('interview-answer').value.trim();
    if (!answer || answer.length < 10) {
        showToast(t('toast_detailed_answer'), 'warning');
        return;
    }
    
    // Stop any active text-to-speech
    window.speechSynthesis.cancel();
    
    // If microphone is active, stop it
    if (isRecognizing && speechRecognition) {
        speechRecognition.stop();
    }
    
    const btn = document.getElementById('btn-submit-answer');
    btn.disabled = true;
    btn.querySelector('.spinner').classList.remove('hidden');
    
    // Hide active box, show streaming card
    document.getElementById('interview-active-question').classList.add('hidden');
    const streamingView = document.getElementById('interview-streaming-view');
    const streamingTextBox = document.getElementById('int-streaming-text');
    
    streamingView.classList.remove('hidden');
    streamingTextBox.innerHTML = `<span class="streaming-loading-indicator">${t('toast_coaching_connect')}</span>`;
    
    let coachingText = '';
    
    try {
        const response = await fetch('/interview/submit-answer-stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                question: currentQuestionObj,
                answer: answer,
                model: activeModel,
                language: currentLanguage
            })
        });
        
        if (!response.ok) throw new Error('API returned an error');
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        
        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            
            buffer += decoder.decode(value, { stream: true });
            
            // Split by double newline (SSE separator)
            let parts = buffer.split('\n\n');
            buffer = parts.pop(); // last partial part
            
            for (const part of parts) {
                const lines = part.split('\n');
                let eventType = '';
                let dataStr = '';
                
                for (const line of lines) {
                    if (line.startsWith('event:')) {
                        eventType = line.replace('event:', '').trim();
                    } else if (line.startsWith('data:')) {
                        dataStr = line.replace('data:', '').trim();
                    }
                }
                
                if (eventType && dataStr) {
                    if (eventType === 'coaching') {
                        try {
                            const textChunk = JSON.parse(dataStr);
                            if (coachingText === '') {
                                streamingTextBox.innerHTML = '';
                            }
                            coachingText += textChunk;
                            streamingTextBox.textContent = coachingText;
                        } catch (e) {
                            console.error('Failed to parse coaching data chunk:', e);
                        }
                    } else if (eventType === 'coaching_done') {
                        // Read feedback aloud on text stream completion
                        speakText(coachingText);
                    } else if (eventType === 'metrics') {
                        try {
                            const feedbackObj = JSON.parse(dataStr);
                            
                            // Save to LocalStorage History
                            saveInterviewHistory(currentQuestionObj, answer, feedbackObj);
                            
                            // Load and transition to static results view
                            setTimeout(() => {
                                streamingView.classList.add('hidden');
                                renderInterviewFeedback(feedbackObj);
                                
                                // Render streaming text block inside feedback card
                                const frameworkCard = document.getElementById('feed-framework-card');
                                const coachingBlockId = 'feed-coaching-text-block';
                                let coachingBlock = document.getElementById(coachingBlockId);
                                if (!coachingBlock) {
                                    coachingBlock = document.createElement('div');
                                    coachingBlock.id = coachingBlockId;
                                    coachingBlock.style.margin = '0 0 1.5rem 0';
                                    coachingBlock.style.padding = '1.2rem 1.5rem';
                                    coachingBlock.style.borderRadius = '12px';
                                    coachingBlock.style.background = 'rgba(255,255,255,0.02)';
                                    coachingBlock.style.border = '1px solid var(--border-glass)';
                                    coachingBlock.style.fontSize = '0.9rem';
                                    coachingBlock.style.lineHeight = '1.6';
                                    frameworkCard.parentNode.insertBefore(coachingBlock, frameworkCard);
                                }
                                coachingBlock.innerHTML = '';
                                const ch3 = document.createElement('h3');
                                ch3.className = 'blue-text';
                                ch3.style.cssText = 'font-family: var(--font-heading); font-size: 1.25rem; font-weight: 600; margin-bottom: 0.8rem; position: relative; padding-bottom: 0.5rem; border-bottom: 1px solid rgba(255,255,255,0.05);';
                                ch3.textContent = t('realtime_coach_feedback');
                                const cp = document.createElement('p');
                                cp.textContent = coachingText;
                                coachingBlock.appendChild(ch3);
                                coachingBlock.appendChild(cp);
                            }, 800);
                        } catch (e) {
                            console.error('Failed to parse feedback metrics:', e);
                        }
                    } else if (eventType === 'error') {
                        showToast(t('toast_feedback_error') + JSON.parse(dataStr), 'error');
                    }
                }
            }
        }
        
    } catch (error) {
        console.error('Submit answer error:', error);
        showToast(t('toast_feedback_error') + error.message, 'error', 8000);
        document.getElementById('interview-active-question').classList.remove('hidden');
        streamingView.classList.add('hidden');
    } finally {
        btn.disabled = false;
        btn.querySelector('.spinner').classList.add('hidden');
    }
}

function renderInterviewFeedback(feedback) {
    document.getElementById('interview-active-question').classList.add('hidden');
    
    // Set score
    const scoreVal = feedback.score;
    document.getElementById('feed-score').textContent = scoreVal.toFixed(1);
    
    // Set verdict
    const verdictTitle = document.getElementById('feed-verdict-title');
    const verdictDesc = verdictTitle.nextElementSibling;
    
    if (scoreVal >= 8.5) {
        verdictTitle.textContent = t('verdict_excellent_title');
        verdictTitle.className = 'green-text';
        verdictDesc.textContent = t('verdict_excellent_desc');
    } else if (scoreVal >= 6.5) {
        verdictTitle.textContent = t('verdict_good_title');
        verdictTitle.className = 'blue-text';
        verdictDesc.textContent = t('verdict_good_desc');
    } else {
        verdictTitle.textContent = t('verdict_needs_coaching_title');
        verdictTitle.className = 'red-text';
        verdictDesc.textContent = t('verdict_needs_coaching_desc');
    }
    
    // Strengths
    const strengthsUl = document.getElementById('feed-strengths');
    strengthsUl.innerHTML = '';
    feedback.strengths.forEach(s => {
        const li = document.createElement('li');
        li.textContent = s;
        strengthsUl.appendChild(li);
    });
    
    // Weaknesses
    const weaknessesUl = document.getElementById('feed-weaknesses');
    weaknessesUl.innerHTML = '';
    feedback.weaknesses.forEach(w => {
        const li = document.createElement('li');
        li.textContent = w;
        weaknessesUl.appendChild(li);
    });
    
    // Keywords Analysis
    const coveredContainer = document.getElementById('feed-covered-keywords');
    const missedContainer = document.getElementById('feed-missed-keywords');

    coveredContainer.innerHTML = '';
    missedContainer.innerHTML = '';

    const allKeywords = currentQuestionObj.ideal_answer_keywords;
    const missed = feedback.missed_keywords && feedback.missed_keywords.length > 0
        ? feedback.missed_keywords
        : [];
    const missedLower = new Set(missed.map(k => k.toLowerCase()));
    const covered = allKeywords.filter(kw => !missedLower.has(kw.toLowerCase()));
    
    if (covered.length === 0) {
        coveredContainer.innerHTML = `<span class="pill-red">${t('none')}</span>`;
    } else {
        covered.forEach(kw => {
            const pill = document.createElement('span');
            pill.className = 'pill-green';
            pill.textContent = kw;
            coveredContainer.appendChild(pill);
        });
    }
    
    if (missed.length === 0) {
        missedContainer.innerHTML = `<span class="pill-green">${t('all_covered')}</span>`;
    } else {
        missed.forEach(kw => {
            const pill = document.createElement('span');
            pill.className = 'pill-red';
            pill.textContent = kw;
            missedContainer.appendChild(pill);
        });
    }
    
    // Suggested framework
    const frameworkCard = document.getElementById('feed-framework-card');
    const frameworkText = document.getElementById('feed-framework');
    if (feedback.suggested_answer_framework) {
        frameworkCard.classList.remove('hidden');
        frameworkText.textContent = feedback.suggested_answer_framework;
    } else {
        frameworkCard.classList.add('hidden');
    }
    
    document.getElementById('interview-feedback-view').classList.remove('hidden');
}

// Storage Session History Functions
async function saveResumeHistory(resumeText, targetRole, modelUsed, analysisResult) {
    const newItem = {
        id: 'res_' + Date.now(),
        date: new Date().toLocaleString(),
        resumeText,
        targetRole,
        modelUsed,
        data: analysisResult
    };
    try {
        await AppDB.save('resume_history', newItem);
    } catch (e) {
        console.error('Failed to save resume history to AppDB, falling back to localStorage:', e);
        try {
            const history = JSON.parse(localStorage.getItem('resume_history') || '[]');
            history.unshift(newItem);
            localStorage.setItem('resume_history', JSON.stringify(history.slice(0, 20)));
        } catch (err) {
            console.error('LocalStorage fallback also failed:', err);
        }
    }
}

// Save interview history
async function saveInterviewHistory(questionObj, answer, feedbackObj) {
    const newItem = {
        id: 'int_' + Date.now(),
        date: new Date().toLocaleString(),
        question: questionObj,
        answer,
        feedback: feedbackObj
    };
    try {
        await AppDB.save('interview_history', newItem);
    } catch (e) {
        console.error('Failed to save interview history to AppDB, falling back to localStorage:', e);
        try {
            const history = JSON.parse(localStorage.getItem('interview_history') || '[]');
            history.unshift(newItem);
            localStorage.setItem('interview_history', JSON.stringify(history.slice(0, 20)));
        } catch (err) {
            console.error('LocalStorage fallback failed:', err);
        }
    }
}

async function renderHistory() {
    const resumeContainer = document.getElementById('resume-history-list');
    const interviewContainer = document.getElementById('interview-history-list');

    let resHistory = [];
    let intHistory = [];

    try {
        resHistory = await AppDB.getAll('resume_history');
        // Sort descending (newest first)
        resHistory.sort((a, b) => b.id.localeCompare(a.id));
    } catch (e) {
        console.error('Failed to load resume history from AppDB, falling back to localStorage:', e);
        resHistory = JSON.parse(localStorage.getItem('resume_history') || '[]');
    }

    try {
        intHistory = await AppDB.getAll('interview_history');
        // Sort descending (newest first)
        intHistory.sort((a, b) => b.id.localeCompare(a.id));
    } catch (e) {
        console.error('Failed to load interview history from AppDB, falling back to localStorage:', e);
        intHistory = JSON.parse(localStorage.getItem('interview_history') || '[]');
    }

    // Render Resume history
    if (resHistory.length === 0) {
        resumeContainer.innerHTML = `<p class="text-muted" style="padding: 1.5rem; text-align: center;">${t('no_resume_history')}</p>`;
    } else {
        resumeContainer.innerHTML = '';
        resHistory.forEach(item => {
            const card = document.createElement('div');
            card.className = 'history-item-card';
            card.onclick = () => loadResumeHistoryItem(item);
            card.innerHTML = `
                <div class="history-item-header">
                    <span class="history-item-title">${item.targetRole}</span>
                    <span class="history-item-date">${item.date}</span>
                </div>
                <div class="history-item-meta">
                    ${t('candidate_label')}: ${item.data.candidate_name || t('not_specified')} | ${t('match_label')}: <span class="green-text" style="font-weight:600;">${Math.round(item.data.skill_analysis.matching_score)}%</span>
                </div>
            `;
            resumeContainer.appendChild(card);
        });
    }

    // Render Interview history
    if (intHistory.length === 0) {
        interviewContainer.innerHTML = `<p class="text-muted" style="padding: 1.5rem; text-align: center;">${t('no_interview_history')}</p>`;
    } else {
        interviewContainer.innerHTML = '';
        intHistory.forEach(item => {
            const card = document.createElement('div');
            card.className = 'history-item-card';
            card.onclick = () => loadInterviewHistoryItem(item);
            card.innerHTML = `
                <div class="history-item-header">
                    <span class="history-item-title">${item.question.target_skill}</span>
                    <span class="history-item-date">${item.date}</span>
                </div>
                <div class="history-item-meta">
                    ${t('score_label')}: <span class="green-text" style="font-weight:600;">${item.feedback.score}/10</span> | ${t('difficulty_label')}: ${item.question.difficulty.toUpperCase()}
                </div>
            `;
            interviewContainer.appendChild(card);
        });
    }
}

function loadResumeHistoryItem(item) {
    document.getElementById('resume-text').value = item.resumeText;
    document.getElementById('resume-target-role').value = item.targetRole;
    
    switchTab('resume');
    renderResumeResults({
        model: item.modelUsed,
        attempts: 1,
        errors: [],
        data: item.data
    });
    showToast(t('loaded_resume_history'), 'success');
}

function loadInterviewHistoryItem(item) {
    currentQuestionObj = item.question;
    
    switchTab('interview');
    
    // Reset other panels
    document.getElementById('interview-empty-state').classList.add('hidden');
    document.getElementById('interview-active-question').classList.add('hidden');
    document.getElementById('interview-streaming-view').classList.add('hidden');
    
    renderInterviewFeedback(item.feedback);
    
    // Remove previous Coach Critique block if present
    const prevBlock = document.getElementById('feed-coaching-text-block');
    if (prevBlock) prevBlock.remove();
    
    showToast(t('loaded_interview_history'), 'success');
}


// BENCHMARKS
async function loadBenchmarkData() {
    const tableBody = document.querySelector('#benchmark-summary-table tbody');
    
    try {
        const response = await fetch('/benchmarks');
        if (!response.ok) throw new Error('Failed to load benchmarks');
        
        const res = await response.json();
        if (!res.success) {
            tableBody.innerHTML = `<tr><td colspan="6" style="text-align:center; color: var(--color-danger);">${res.error}</td></tr>`;
            return;
        }
        
        const data = res.data;
        processAndRenderBenchmarks(data);
        
    } catch (error) {
        console.error('Load benchmark data error:', error);
        tableBody.innerHTML = `<tr><td colspan="6" style="text-align:center; color: var(--color-danger);">${t('benchmark_error')}</td></tr>`;
    }
}

function processAndRenderBenchmarks(rawRuns) {
    // Group by model name
    const modelsMap = {};
    
    rawRuns.forEach(run => {
        const m = run.model;
        if (!modelsMap[m]) {
            modelsMap[m] = {
                name: m,
                tps: [],
                ttft: [],
                vram: [],
                ram: [],
                successes: 0,
                total: 0
            };
        }
        
        modelsMap[m].total++;
        if (run.success) {
            modelsMap[m].successes++;
            if (run.tokens_per_second > 0) modelsMap[m].tps.push(run.tokens_per_second);
            if (run.time_to_first_token_s > 0) modelsMap[m].ttft.push(run.time_to_first_token_s);
        }
        
        if (run.peak_vram_mb > 0) modelsMap[m].vram.push(run.peak_vram_mb);
        if (run.peak_ram_mb > 0) modelsMap[m].ram.push(run.peak_ram_mb);
    });
    
    // Calculate averages
    const summary = Object.values(modelsMap).map(m => {
        const avgTps = m.tps.length > 0 ? (m.tps.reduce((a,b)=>a+b, 0) / m.tps.length) : 0.0;
        const avgTtft = m.ttft.length > 0 ? (m.ttft.reduce((a,b)=>a+b, 0) / m.ttft.length) : 0.0;
        // Peak values are more descriptive for memory spikes
        const maxVram = m.vram.length > 0 ? Math.max(...m.vram) : 0.0;
        const maxRam = m.ram.length > 0 ? Math.max(...m.ram) : 0.0;
        const compliance = m.total > 0 ? (m.successes / m.total * 100) : 0.0;
        
        return {
            name: m.name,
            tps: avgTps,
            ttft: avgTtft,
            vram: maxVram,
            ram: maxRam,
            compliance: compliance
        };
    });
    
    // Render table
    const tableBody = document.querySelector('#benchmark-summary-table tbody');
    tableBody.innerHTML = '';
    
    summary.forEach(s => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><strong>${s.name}</strong></td>
            <td><span class="green-text" style="font-weight:600;">${s.tps.toFixed(1)} tok/s</span></td>
            <td>${s.ttft.toFixed(3)}s</td>
            <td>${s.vram > 0 ? s.vram.toFixed(0) + ' MB' : '0 MB (CPU)'}</td>
            <td>${s.ram.toFixed(0)} MB</td>
            <td><span class="badge" style="background:${s.compliance === 100 ? 'var(--color-success-glow)' : 'rgba(255,255,255,0.05)'}; border-color:${s.compliance === 100 ? 'var(--color-success)' : 'var(--border-glass)'}">${s.compliance.toFixed(0)}%</span></td>
        `;
        tableBody.appendChild(tr);
    });
    
    // Find maximums for scaling charts
    const maxTps = Math.max(...summary.map(s => s.tps), 1);
    const maxTtft = Math.max(...summary.map(s => s.ttft), 1);
    const maxMem = Math.max(...summary.map(s => s.vram + s.ram), 1);
    
    // Render Charts
    renderTpsChart(summary, maxTps);
    renderTtftChart(summary, maxTtft);
    renderMemoryChart(summary, maxMem);
    renderComplianceChart(summary);
}

function renderTpsChart(summary, maxTps) {
    const container = document.getElementById('chart-tps');
    container.innerHTML = '';
    
    // Sort by TPS descending
    const sorted = [...summary].sort((a,b) => b.tps - a.tps);
    
    sorted.forEach(s => {
        const pct = (s.tps / maxTps * 100).toFixed(0);
        const row = document.createElement('div');
        row.className = 'chart-bar-row';
        row.innerHTML = `
            <div class="bar-label">${s.name}</div>
            <div class="bar-track">
                <div class="bar-fill" style="width: 0%"></div>
            </div>
            <div class="bar-value">${s.tps.toFixed(1)} t/s</div>
        `;
        container.appendChild(row);
        
        // Micro-animation trigger
        requestAnimationFrame(() => {
            setTimeout(() => {
                const el = row.querySelector('.bar-fill');
                if (el) el.style.width = `${pct}%`;
            }, 50);
        });
    });
}

function renderTtftChart(summary, maxTtft) {
    const container = document.getElementById('chart-ttft');
    container.innerHTML = '';
    
    // Sort by TTFT ascending (lower latency first)
    const sorted = [...summary].sort((a,b) => a.ttft - b.ttft);
    
    sorted.forEach(s => {
        const pct = (s.ttft / maxTtft * 100).toFixed(0);
        const row = document.createElement('div');
        row.className = 'chart-bar-row';
        row.innerHTML = `
            <div class="bar-label">${s.name}</div>
            <div class="bar-track">
                <div class="bar-fill warning" style="width: 0%"></div>
            </div>
            <div class="bar-value">${s.ttft.toFixed(3)}s</div>
        `;
        container.appendChild(row);
        
        // Micro-animation trigger
        requestAnimationFrame(() => {
            setTimeout(() => {
                const el = row.querySelector('.bar-fill');
                if (el) el.style.width = `${pct}%`;
            }, 50);
        });
    });
}

function renderMemoryChart(summary, maxMem) {
    const container = document.getElementById('chart-memory');
    container.innerHTML = '';
    
    summary.forEach(s => {
        const total = s.vram + s.ram;
        const vramPct = (s.vram / maxMem * 100).toFixed(0);
        const ramPct = (s.ram / maxMem * 100).toFixed(0);
        
        const row = document.createElement('div');
        row.className = 'chart-bar-row';
        row.innerHTML = `
            <div class="bar-label">${s.name}</div>
            <div class="bar-track" style="display:flex; border:none; background:transparent;">
                <div class="bar-fill" style="width: 0%; border-radius: 4px 0 0 4px; background:var(--color-primary);"></div>
                <div class="bar-fill warning" style="width: 0%; border-radius: 0 4px 4px 0; background:var(--color-info);"></div>
            </div>
            <div class="bar-value" style="font-size:0.75rem;">${total.toFixed(0)}MB</div>
        `;
        container.appendChild(row);
        
        // Micro-animation trigger
        requestAnimationFrame(() => {
            setTimeout(() => {
                const elements = row.querySelectorAll('.bar-fill');
                if (elements.length >= 2) {
                    elements[0].style.width = `${vramPct}%`;
                    elements[1].style.width = `${ramPct}%`;
                }
            }, 50);
        });
    });
}

function renderComplianceChart(summary) {
    const container = document.getElementById('chart-compliance');
    container.innerHTML = '';
    
    summary.forEach(s => {
        const row = document.createElement('div');
        row.className = 'chart-bar-row';
        
        let barClass = 'success';
        if (s.compliance < 100) barClass = 'warning';
        if (s.compliance < 50) barClass = 'danger';
        
        row.innerHTML = `
            <div class="bar-label">${s.name}</div>
            <div class="bar-track">
                <div class="bar-fill ${barClass}" style="width: 0%"></div>
            </div>
            <div class="bar-value">${s.compliance.toFixed(0)}%</div>
        `;
        container.appendChild(row);
        
        // Micro-animation trigger
        requestAnimationFrame(() => {
            setTimeout(() => {
                const el = row.querySelector('.bar-fill');
                if (el) el.style.width = `${s.compliance}%`;
            }, 50);
        });
    });
}
