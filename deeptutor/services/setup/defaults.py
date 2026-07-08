"""Static setup defaults shared by setup/init and config/loader."""

from __future__ import annotations

DEFAULT_INTERFACE_SETTINGS = {
    "theme": "snow",
    "language": "en",
    "sidebar_description": "✨ Data Intelligence Lab @ HKU",
    "sidebar_nav_order": {
        "start": ["/", "/history", "/knowledge", "/notebook"],
        "learnResearch": ["/question", "/solver", "/research", "/co_writer"],
    },
}

DEFAULT_MAIN_SETTINGS = {
    "system": {
        "language": "en",
    },
    "logging": {
        "level": "WARNING",
        "save_to_file": True,
        "console_output": True,
    },
    "tools": {
        "run_code": {
            "allowed_roots": ["./data/user"],
        },
        "web_search": {
            "enabled": True,
        },
    },
    "capabilities": {
        "solve": {
            "max_rounds": 12,
            "max_replans": 2,
        },
        "research": {
            "researching": {
                "note_agent_mode": "auto",
                "tool_timeout": 60,
                "tool_max_retries": 2,
                "paper_search_years_limit": 3,
            },
        },
        "question": {
            "exploring": {
                "max_iterations": 8,
                "tool_summarizer": {
                    "enabled": True,
                    "max_tokens": 800,
                },
            },
        },
    },
}

DEFAULT_AGENTS_SETTINGS = {
    "capabilities": {
        "solve": {"temperature": 0.3, "max_tokens": 8192},
        "research": {"temperature": 0.5, "max_tokens": 12000},
        "question": {"temperature": 0.7, "max_tokens": 4096},
        "co_writer": {"temperature": 0.7, "max_tokens": 4096},
        "visualize": {"temperature": 0.4, "max_tokens": 16384},
        "chat": {
            "temperature": 0.2,
            "responding": {"max_tokens": 8000},
        },
    },
    "tools": {
        "brainstorm": {"temperature": 0.8, "max_tokens": 2048},
    },
    "services": {
        "personalization": {"temperature": 0.5, "max_tokens": 8192},
    },
    "plugins": {
        "vision_solver": {"temperature": 0.3, "max_tokens": 12000},
        "math_animator": {"temperature": 0.4, "max_tokens": 12000},
    },
}
