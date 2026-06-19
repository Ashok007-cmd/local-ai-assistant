# Contributing to Local AI Assistant

Thank you for your interest in contributing to our open-source project! We want to make contributing as easy and transparent as possible.

## Code of Conduct
Please read and follow our [Code of Conduct](CODE_OF_CONDUCT.md) in all community interactions.

## Branch Strategy
*   `main` is the stable production branch.
*   Create feature branches (`feature/your-feature-name`) or bugfix branches (`bugfix/bug-name`) from `main`.
*   Submit Pull Requests targeting `main`.

## Local Setup
1.  **Clone the Repo**:
    ```bash
    git clone https://github.com/your-username/project-2-local-ai-assistant.git
    cd project-2-local-ai-assistant
    ```
2.  **Install Requirements**:
    Initialize a virtual environment and install packages:
    ```bash
    python -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    ```
3.  **Run Development Server**:
    Ensure local Ollama is running (`ollama serve`) or configure `GEMINI_API_KEY` in your environment.
    ```bash
    uvicorn src.app:app --reload
    ```

## Development Guidelines
*   **Testing**: Write tests for any new features or bug fixes. Run tests with `python -m pytest`.
*   **Code Style**: Adhere to PEP 8 standards. Use strict typing annotations where possible.
*   **Commits**: Write clear, imperative-style commit messages (e.g. `feat: add Speech Synthesis support for mock interviewer`).
