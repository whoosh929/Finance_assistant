import logging
import json

from ai.open_ai.configuration import OpenAIConfiguration
from ai.abstract_ai import AbstractAI
from ai.ai_result import AIResult

from ai.open_ai.tools.debugging.exception_debugger import ExceptionDebugger
from ai.open_ai.utilities.chat_completion import OpenAIChatCompletion
from ai.open_ai.task_refinement.step import Step
from ai.open_ai.utilities.open_ai_utilities import (
    get_openai_api_key,
    get_tool_by_function_name,
)
from ai.open_ai.tools.function_caller import call_function
from ai.open_ai.utilities.system_info import SystemInfo

from utilities.pretty_print import pretty_print_conversation


class TaskRefiner:
    def __init__(self, json_args, system_info = None):        
        self.configuration = OpenAIConfiguration(json_args)
        # Add another local var for accessing the list of tools we can suggest
        self.suggested_functions = json_args["suggested_functions"]

        self.openai_api_key = get_openai_api_key()

        if system_info is None:
            self.system_info = SystemInfo()
        else:
            self.system_info = system_info

        self.open_ai_completion = OpenAIChatCompletion(
            self.openai_api_key, self.configuration.model
        )

        # if logging.getLogger().isEnabledFor(logging.DEBUG):
        #     self.exception_debugger = ExceptionDebugger(
        #         self.openai_api_key, self.configuration.model
        #     )

    def break_task_into_steps(self, input, parent_step, recurse=False) -> Step:
        messages = []
        messages.append(
            {
                "role": "assistant",
                "content": "I am helping another digital assistant to answer a query.",
            }
        )
        messages.append(
            {
                "role": "assistant",
                "content": "I will take the following request and break it into smaller pieces where it makes sense in order to develop a plan to answer this query.",
            }
        )
        messages.append(
            {
                "role": "assistant",
                "content": "I will break the query up into steps that utilize the functions available to me, where possible (keeping the related function calls together).",
            }
        )
        messages.append({"role": "user", "content": "Query: " + input})
        messages.append(
            {
                "role": "assistant",
                "content": "Ok, I have the query. If I can't break the steps down any further, or if I know how to resolve the step through my own knowledge, I will just print 'done'.",
            }
        )
        messages.append(
            {
                "role": "assistant",
                "content": "Here is a list of the steps that an assistant would need to take to answer the query (I will call the 'create_list' function to print these).",
            }
        )
        messages.append(
            {
                "role": "assistant",
                "content": "I have re-ordered the steps in a way that makes logical sense (where necessary).",
            }
        )
        messages.append(
            {
                "role": "assistant",
                "content": "I have also made sure that each step contains enough information to allow that step to be addressed independently of information in other steps, relying only on the output of the previous step.",
            }
        )
        messages.append(
            {
                "role": "assistant",
                "content": "Additionally, I have ensured that each step does not contain any additional instructions or information that was not included in the initial query.",
            }
        )

        list_tool = get_tool_by_function_name("create_list", self.configuration.tools)
        tool_recommender = get_tool_by_function_name(
            "recommend_tool", self.configuration.tools
        )

        # prompt the ai to generate steps
        result = self.process(messages, True, [list_tool, tool_recommender])[-1]

        if "function_call" in result:
            if result["function_call"]["name"] == "create_list":
                # call the list function with the steps
                steps = call_function(result["function_call"], self.configuration.tools)

                if len(steps) == 0:
                    # We are at the bottom of this branch
                    return

                # Create a list of step objects
                for s in steps:
                    recommended_tool = self.evaluate_for_possible_tool_use(s)
                    if "function_call" in recommended_tool:
                        new_step = Step(
                            s,
                            call_function(
                                recommended_tool["function_call"],
                                self.configuration.tools,
                            ),
                        )
                        parent_step.sub_steps.append(new_step)
                        continue
                    else:
                        # no tool was recommended, see if we can break it down further
                        new_step = Step(s)
                        parent_step.sub_steps.append(new_step)
                        if recurse:
                            self.break_task_into_steps(s, new_step, recurse)

        # If any of the sub-steps are using the same tool, combine that step into one step
        parent_step = self.combine_steps_using_same_tool(parent_step)

        return parent_step

    def combine_steps_using_same_tool(self, parent_step):
        # If any of the sub-steps are using the same tool, combine that step into one step
        for s in parent_step.sub_steps:
            if s.recommended_tool.lower() is not None:
                for s2 in parent_step.sub_steps:
                    if (
                        s2.recommended_tool.lower() is not None
                        and s2.recommended_tool.lower() == s.recommended_tool.lower()
                        and s2 != s
                    ):
                        # Combine the steps
                        s.step = s.step + " " + s2.step
                        parent_step.sub_steps.remove(s2)

        # Rephrase the steps to make them more natural after combining
        for s in parent_step.sub_steps:
            s.step = self.rephrase_step(s.step)            

        return parent_step

    def rephrase_step(self, step):
        messages = []
        messages.append(
            {
                "role": "assistant",
                "content": "I am helping a user to rephrase some text so that it is more natural.",
            }
        )
        messages.append(
            {
                "role": "assistant",
                "content": "I will take the following text and rephrase it so that any goals are stated unambiguously, the statement is made using good grammar, and punctuation is corrected.",
            }
        )
        messages.append({"role": "user", "content": step})
        messages.append(
            {
                "role": "assistant",
                "content": "Here is the rephrased text:",
            }
        )

        return self.process(messages)[-1]

    def evaluate_for_possible_tool_use(self, step):
        # For each of the steps we should evaluate it for possible tool use.
        # If a tool can be used for the step, we don't need to break it down further
        messages = []
        messages.append(
            {
                "role": "assistant",
                "content": "Available tools:",
            }
        )
        for function_details in self.suggested_functions:
            messages.append(
                {
                    "role": "assistant",
                    "content": f"function: '{function_details['name']}', description: '{function_details['description']}'",
                }
            )
        messages.append(
            {
                "role": "assistant",
                "content": "Given the above list of tools, I will evaluate the following input to see if any tool can be used to accomplish the stated goal:",
            }
        )
        messages.append({"role": "user", "content": step})
        messages.append(
            {
                "role": "assistant",
                "content": "My tool recommendation is (I will print 'none' if I can't figure out which tool to use):",
            }
        )

        return self.process(messages)[-1]

    def process(self, messages: list, use_functions=True, specific_functions=None):
        # Always prepend a message with some basic info
        temp_messages = messages.copy()
        temp_messages.insert(
            0,
            {
                "role": "system",
                "content": self.system_info.get(),
            },
        )

        try:
            if use_functions:
                if specific_functions:
                    chat_response = self.open_ai_completion.chat_completion_request(
                        temp_messages,
                        functions=specific_functions,
                    )
                else:
                    chat_response = self.open_ai_completion.chat_completion_request(
                        temp_messages,
                        functions=[t.open_ai_tool for t in self.configuration.tools],
                    )
            else:
                chat_response = self.open_ai_completion.chat_completion_request(
                    temp_messages
                )

            if chat_response.status_code != 200:
                raise Exception(
                    f"OpenAI returned a non-200 status code: {chat_response.status_code}.  Response: {chat_response.text}"
                )

            assistant_message = chat_response.json()["choices"][0]["message"]
            messages.append(assistant_message)
            pretty_print_conversation(messages)

            return messages

        except Exception as e:
            logging.error(e)
            # if self.exception_debugger:
            #     _ = self.exception_debugger.debug_exception(e, print_summary=True)


# def evaluate_conversation_for_next_step(self, current_conversation, steps):
#         # Evaluate the current conversation for the next step needed to complete the task
#         messages = []
#         messages.append(
#             {
#                 "role": "assistant",
#                 "content": "I need to evaluate the conversation to see which step I am on.",
#             }
#         )
#         messages.append(
#             {
#                 "role": "assistant",
#                 "content": "The current state of the conversation is:",
#             }
#         )

#         for c in current_conversation:
#             messages.append(c)

#         messages.append(
#             {
#                 "role": "assistant",
#                 "content": "The steps needed to complete the task are:",
#             }
#         )
#         for s in steps:
#             messages.append(s)

#         messages.append(
#             {
#                 "role": "assistant",
#                 "content": "I will return the next step in the list that has not been completed, or 'done' if the task is complete.",
#             }
#         )

#         return self.process(messages)[-1]


# def evaluate_progress(self, initial_request, current_conversation):
#         # Create a new chain of messages to evaluate the progress
#         messages = []
#         messages.append(
#             {
#                 "role": "assistant",
#                 "content": "I need to evaluate the progress of an AI assistant in resolving a user's query.",
#             }
#         )

#         messages.append({"role": "assistant", "content": "The initial request was:"})
#         messages.append({"role": "assistant", "content": initial_request})

#         messages.append(
#             {
#                 "role": "assistant",
#                 "content": "The current state of the conversation is:",
#             }
#         )

#         for c in current_conversation:
#             messages.append(c)

#         messages.append({"role": "assistant","content": "If the assistant is done, I will respond ONLY with 'done'.",})
#         messages.append({"role": "assistant","content": "If the assistant is not done, I will respond with the necessary instructions to complete the task.",})

#         return self.process(messages, False)[-1]
