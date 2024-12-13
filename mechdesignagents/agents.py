from autogen import AssistantAgent, UserProxyAgent
from autogen.agentchat.contrib.retrieve_user_proxy_agent import RetrieveUserProxyAgent
from ocp_vscode import *
from autogen.agentchat.contrib.multimodal_conversable_agent import MultimodalConversableAgent

import os
from typing_extensions import Annotated
from langchain_rag import langchain_rag
from llm import LLMConfigSelector

#Definig default config list for llms. Add more llms if you want. By default
#Autogen will select the first one until it can use it.
config_list_selection = LLMConfigSelector()
llm_config = {
    "seed": 25,
    "temperature": 0.3,
    "config_list": [config_list_selection.get_model_config()],
    # "request_timeout": 600,
    # "retry_wait_time": 120,
}

#This is for terminating the chat. This can be passed as one line functin as well.
def termination_msg(x):
    return isinstance(x, dict) and "TERMINATE" == str(x.get("content", ""))[-9:].upper()

#Defining agents for designing
#First we define designer userproxy agent which takes input from human

User = UserProxyAgent(
    name="User",
    is_termination_msg=termination_msg,
    human_input_mode="ALWAYS", # Use ALWAYS for human in the loop
    max_consecutive_auto_reply=5, #Change it to limit the number of replies from this agent
    #here we define the coding configuration for executing the code generated by agent 
    # code_execution_config= {
    #     "work_dir": "NewCADs",
    #     "use_docker": False,
    # },
    code_execution_config= False,
    # llm_config={"config_list": config_list}, #you can also select a particular model from the config list here for llm
    system_message=""" A human designer who asks questions to create CAD models using CadQuery. Interact with Designer Expert
    on how to create the cad model. The Designer Expert's approach to create models needs to be
    approved by this Designer. """,
    # description= "The designer who asks questions to create CAD models using CadQuery",
    # default_auto_reply="Reply `TERMINATE` if the task is done.",
)

proxy_user = UserProxyAgent(
    name="Proxy_User",
    is_termination_msg=termination_msg,
    human_input_mode="NEVER", # Use ALWAYS for human in the loop
    max_consecutive_auto_reply=5, #Change it to limit the number of replies from this agent
    #here we define the coding configuration for executing the code generated by agent 
    # code_execution_config= {
    #     "work_dir": "NewCADs",
    #     "use_docker": False,
    # },
    code_execution_config= False,
    # llm_config={"config_list": config_list}, #you can also select a particular model from the config list here for llm
    # system_message=""" A human designer who asks questions to create CAD models using CadQuery. Interact with Designer Expert
    # on how to create the cad model. The Designer Expert's approach to create models needs to be
    # approved by this Designer. """,
    # description= "The designer who asks questions to create CAD models using CadQuery",
    # default_auto_reply="Reply `TERMINATE` if the task is done.",
)

functioncall_agent = AssistantAgent(
    name = "Function_Call_Agent",
    is_termination_msg=termination_msg,
    human_input_mode="NEVER",
    llm_config= llm_config,
    system_message="You are cad function or tool calling agent. You are provided with functions"
    "to create CAD models. Given the design problem for which a function is registered, call the function."
    "If the parameters for the function are not specified by the user, give parameteres yourself."
    "If you do not have the function registered with to create certain CAD model, pass the problem to Designer Expert explicitly."
    "If the function is called successfully then TERMINATE the chat.",
    description="The Function Call Agent that calls registered function to create cad models."

)   

designer_expert = AssistantAgent(
    name="Designer_Expert",
    is_termination_msg=termination_msg,
    human_input_mode="NEVER", # Use ALWAYS for human in the loop
    llm_config=llm_config, #you can also select a particular model from the config list here for llm
    system_message="""You are a CAD Design Expert who provides concise plan and directions to support CAD modeling in CadQuery. 
    You should also revise the approach based on feedback from designer. Explain in clear steps what
    needs to be done by CadQuery Code Writer. 
    For each design request:
    Clearly list the necessary parameters.
    Offer a single, focused design approach using CadQuery-specific methods or geometry data only.
    Structure responses as: Required Parameters: [list essential parameters] Design Approach: [CadQuery-driven approach, structured into logical steps]

    Example: Q: Create a cylinder. A: Required Parameters: radius, height Design Approach: Use CadQuery to create a base circle and extrude it upward to the specified height.

    Keep answers brief, direct, and strictly analytical to aid smooth CadQuery implementation.
    NEVER provide code.""",
    description= "The designer expert who provides approach to answer questions to create CAD models in CadQuery",
)

#Here we define our RAG agent. 
designer_aid  = RetrieveUserProxyAgent(
    name="Designer_Assistant",
    is_termination_msg=termination_msg,
    human_input_mode="NEVER",
    llm_config=llm_config,
    default_auto_reply="Reply `TERMINATE` if the task is done.",
    code_execution_config=False,
    retrieve_config={
        "task": "code",
        "docs_path":[
            "/home/niel77/MechanicalAgents/data/code_documentation.pdf",#change this to input any file you want for RAG
            ],
        "chunk_token_size" : 500,
        "collection_name" : "groupchat",
        "get_or_create": True,
        "customized_prompt":'''You provide the relvant codes for creating the CAD models in CadQuery from the 
        documentation provided.''',
    },
)

cad_coder_assistant = AssistantAgent(
    name="CAD_coder_assistant",
    system_message="Only use the function you have been provided with."
    "First try to find the code for model to be created using the function provided."
    "For example if a box has to be created search about creating the box with the function provided before moving to the next step."
    "If nothing relevant code found for the model, search for the codes to perform tasks specified by Designer Expert, only use "
    "the functions you have been provided with. Do not "
    "reply with helpful tips. Once you've recommended functions and got the response pass the summarized result to the CAD coder agent ",
    llm_config=llm_config,
    description="The CAD coder assistant which uses function or tool call (calls call_rag function) to search the code for cad model generation"
)

@cad_coder_assistant.register_for_execution()
@cad_coder_assistant.register_for_llm(description= "Code finder using Retrieval Augmented Generation")
def call_rag(
    question: Annotated[float, "Task for which code to be found"],
) -> str:
    return langchain_rag(question)

cad_coder = AssistantAgent(
    "CadQuery_Code_Writer",
    system_message= """You follow the approved plan by Designer Expert.
    You write python code to create CAD models using CadQuery.
    Wrap the code in a code block that specifies the script type. 
    The user can't modify your code. 
    So do not suggest incomplete code which requires others to modify. 
    Don't use a code block if it's not intended to be executed by the executor.
    Don't include multiple code blocks in one response. 
    Do not ask others to copy and paste the result. 
    Check the execution result returned by the executor.
    If the result indicates there is an error, fix the error and output the code again.
    Suggest the full code instead of partial code or code changes. 
    For every response, use this format in Python markdown:
        Adhere strictly to the following outline
        Python Markdown and File Name
        Start with ```python and # filename: <design_name>.py (based on model type).

        Import Libraries
        ALWAYS import cadquery and ocp_vscode (for visualization).

        Define Parameters
        List dimensions or properties exactly as instructed by the analyst.

        Create the CAD Model
        Build models using only CadQuery’s primitives and boolean operations as directed.

        Save the Model
        Export in STL, STEP, and DXF formats.

        Visualize the Model
        Use show(model_name) from ocp_vscode to visualize.

        Example:
```
        python
        # filename: box.py
        import cadquery as cq
        from ocp_vscode import * #never forget this line

        # Step 1: Define Parameters
        height = 60.0
        width = 80.0
        thickness = 10.0

        # Step 2: Create the CAD Model
        box = cq.Workplane("XY").box(height, width, thickness)

        # Step 3: Save the Model
        cq.exporters.export(box, "box.stl")
        cq.exporters.export(box.section(), "box.dxf")
        cq.exporters.export(box, "box.step")

        # Step 4: Visualize the Model
        show(box) #always visualize the model
```
        Only use CadQuery’s predefined shapes and operations based on the analyst’s instructions.""",
    llm_config=llm_config,
    human_input_mode="NEVER",
    description="CadQuery Code Writer who writes python code to create CAD models following the system message.",
)


executor = AssistantAgent(
    name="Executor",
    is_termination_msg=termination_msg,
    system_message="You save and execute the code written by the CadQuery Code Writer and report and save the result and pass it to Reviewer.",
    code_execution_config= {
        "last_n_messages": 3,
        "work_dir": "NewCADs",
        "use_docker": False,
        
    },
    description= "Executor who executes the code written by CadQuery Code Writer."
)
reviewer = AssistantAgent(
    name="Reviewer",
    is_termination_msg=termination_msg,
    system_message=''' If code ran successfully, just pass message that it ran successfully to User for final feedback.
    IF execution fails,then only you suggest changes to code written by CadQuery Code Writer
    making sure that CadQuery Code Writer is using methods and functions available within CadQuery library
    for recreating the cad model specified by User and using show method from ocp_vscode library to visualize the model.
    ''' ,
    llm_config=llm_config,
    description="Code Reviewer who can review python code written by CadQuery Code Writer after executed by Executor.",
)

cad_reviewer= MultimodalConversableAgent(
    name= "CAD_Recognition_Agent",
    # is_termination_msg=lambda x: x.get("content", "").rstrip().endswith("TERMINATE"),
    human_input_mode="NEVER",
    code_execution_config = False,
    llm_config=llm_config,
    system_message="""
    You review the cad generated by analyzing the image provided to you to check if the created CAD model is as per the request of the User.
    If the generated CAD model does not looks like what is required, provide information regarding the required changes 
    to be made for correct model generation. You will be provided image path by the User.
    """
)

#clears the history of the old chats
def reset_agents():
    User.reset()
    designer_aid.reset()
    cad_coder_assistant.reset()
    executor.reset()
    cad_coder.reset()
    reviewer.reset()
    designer_expert.reset()


