import logging
import streamlit as st
import os

from src.configuration.assistant_configuration import (
    RetrievalAugmentedGenerationConfigurationLoader,
)

from src.ai.interactions.interaction_manager import InteractionManager
from src.ai.tools.tool_manager import ToolManager


def get_rag_configuration():
    """Loads the configuration from the path"""
    rag_config_path = os.environ.get(
        "RAG_CONFIG_PATH",
        "configurations/rag_configs/openai_rag.json",
    )

    return RetrievalAugmentedGenerationConfigurationLoader.from_file(rag_config_path)


def settings_page():
    st.title("Settings")
    settings_tab, tools_tab = st.tabs(["General Settings", "Tools"])

    with settings_tab:
        general_settings()

    with tools_tab:
        tools_settings()


def tools_settings():
    tool_manager = ToolManager()

    tools = tool_manager.get_all_tools()

    # Create a toggle to enable/disable each tool
    for tool in tools:
        st.toggle(
            tools[tool]["display_name"],
            help=tools[tool]["help_text"],
            value=tool_manager.is_tool_enabled(tool),
            key=tool,
            on_change=tool_manager.toggle_tool,
            kwargs={"tool_name": tool},
        )

def general_settings():
    source_control_options = ["GitLab", "GitHub"]
    source_control_provider = st.selectbox(
        "Source Control Provider",
        source_control_options,
        index=source_control_options.index(
            os.getenv("SOURCE_CONTROL_PROVIDER", "GitHub")
        ),
    )

    # Source Code URL
    source_code_url = st.text_input("Source Code URL", os.getenv("SOURCE_CONTROL_URL"))

    # Source Code Personal Access Token (PAT)
    pat = st.text_input(
        "Source Code Personal Access Token (PAT)",
        type="password",
        value=os.getenv("SOURCE_CONTROL_PAT"),
    )

    # Debug Logging
    logging_options = ["DEBUG", "INFO", "WARN"]
    debug_logging = st.selectbox(
        "Logging Level",
        logging_options,
        index=logging_options.index(os.getenv("LOGGING_LEVEL", "INFO")),
    )

    # LLM Model selection box
    # llm_model_options = ["gpt-3.5-turbo-16k", "gpt-3.5-turbo", "gpt-4"]
    # llm_model = st.selectbox("LLM Model", llm_model_options, index=llm_model_options.index(os.getenv("LLM_MODEL", "gpt-3.5-turbo")))

    # Save button
    if st.button("Save Settings"):
        # Set the environment variables
        os.environ["SOURCE_CONTROL_PROVIDER"] = source_control_provider

        if source_code_url:
            os.environ["SOURCE_CONTROL_URL"] = source_code_url

        if pat:
            os.environ["SOURCE_CONTROL_PAT"] = pat

        os.environ["LOGGING_LEVEL"] = str(debug_logging)
        logging.basicConfig(level=debug_logging)

        # os.environ["LLM_MODEL"] = llm_model

        # Process and save the settings here (e.g., to a file or database)
        # For demonstration purposes, we'll just print them
        print(
            f"SOURCE_CONTROL_PROVIDER: {os.getenv('SOURCE_CONTROL_PROVIDER', 'NOT SET')}"
        )
        print(f"SOURCE_CONTROL_URL: {os.getenv('SOURCE_CONTROL_URL', 'NOT SET')}")
        print(f"SOURCE_CONTROL_PAT: {os.getenv('SOURCE_CONTROL_PAT', 'NOT SET')}")
        print(f"LOGGING_LEVEL: {os.getenv('LOGGING_LEVEL', 'NOT SET')}")
        # print(f"LLM_MODEL: {os.getenv('LLM_MODEL', 'NOT SET')}")


# Run the settings page
if __name__ == "__main__":
    settings_page()
