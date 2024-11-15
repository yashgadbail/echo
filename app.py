import os
import asyncio
from openai import AsyncAzureOpenAI

import chainlit as cl
from uuid import uuid4
from chainlit.logger import logger

from realtime import RealtimeClient
from realtime.tools import tools

client = AsyncAzureOpenAI(api_key=os.environ["AZURE_OPENAI_API_KEY"],
                          azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
                          azure_deployment=os.environ["AZURE_OPENAI_DEPLOYMENT"],
                          api_version="2024-10-01-preview")    

async def setup_openai_realtime(system_prompt: str):
    """Instantiate and configure the OpenAI Realtime Client"""
    openai_realtime = RealtimeClient(system_prompt = system_prompt)
    cl.user_session.set("track_id", str(uuid4()))
    
    async def handle_conversation_updated(event):
        item = event.get("item")
        delta = event.get("delta")
        """Currently used to stream audio back to the client."""
        if delta:
            # Only one of the following will be populated for any given event
            if 'audio' in delta:
                audio = delta['audio']  # Int16Array, audio added
                await cl.context.emitter.send_audio_chunk(cl.OutputAudioChunk(mimeType="pcm16", data=audio, track=cl.user_session.get("track_id")))
                
            if 'arguments' in delta:
                arguments = delta['arguments']  # string, function arguments added
                pass
            
    async def handle_item_completed(item):
        """Generate the transcript once an item is completed and populate the chat context."""
        try:
            transcript = item['item']['formatted']['transcript']
            if transcript != "":
                await cl.Message(content=transcript).send()
        except:
            pass
    
    async def handle_conversation_interrupt(event):
        """Used to cancel the client previous audio playback."""
        cl.user_session.set("track_id", str(uuid4()))
        await cl.context.emitter.send_audio_interrupt()
        
    async def handle_input_audio_transcription_completed(event):
        item = event.get("item")
        delta = event.get("delta")
        if 'transcript' in delta:
            transcript = delta['transcript']
            if transcript != "":
                await cl.Message(author="You", type="user_message", content=transcript).send()
        
    async def handle_error(event):
        logger.error(event)
        
    
    openai_realtime.on('conversation.updated', handle_conversation_updated)
    openai_realtime.on('conversation.item.completed', handle_item_completed)
    openai_realtime.on('conversation.interrupted', handle_conversation_interrupt)
    openai_realtime.on('conversation.item.input_audio_transcription.completed', handle_input_audio_transcription_completed)
    openai_realtime.on('error', handle_error)

    cl.user_session.set("openai_realtime", openai_realtime)
    coros = [openai_realtime.add_tool(tool_def, tool_handler) for tool_def, tool_handler in tools]
    await asyncio.gather(*coros)
    

system_prompt = """
Act as a friendly and efficient voice assistant within the GreenLink dashboard, helping John Deere customers, drivers, and operators with real-time information, guidance, and quick actions based on their spoken requests. Use available tools (like product search via `pgvector` and weather services) and accessible data (such as model and farm location) to deliver fast, accurate, and context-aware responses.

### Steps

1. **Listen and Interpret the Request:** Recognize and interpret the customer’s spoken request, identifying the type of information or action they need (e.g., product help, troubleshooting, or local weather).
2. **Use Data and Tools Smartly:** 
   - **Product or Service Information:** Access the `pgvector` tool to search for product-specific details, manuals, or guides.
   - **Weather Updates:** For requests about weather, use the weather tool to fetch relevant, location-based forecasts for the customer’s farm.
3. **Respond Clearly and Concisely:** Speak back in a clear, conversational tone, providing direct, actionable information or guidance relevant to their query.
4. **Encourage Follow-Up:** Let them know they can ask for further assistance or other dashboard features if needed.
5. **Close with Friendly Reassurance:** End responses with a polite, helpful closing that reassures the user they’re supported by John Deere.

### Output Format

Provide responses as short, clear voice statements that:
- Acknowledge the user's question or issue with warmth and professionalism
- Provide specific information or guidance based on available data and tools
- Invite further inquiries or provide related options if applicable
- Use a friendly and helpful tone to leave the user feeling supported

### Notes
- **Greeting:** For first-time interactions, begin with a friendly “Hello! Welcome to GreenLink by John Deere.”
- **Privacy and Data Handling:** Handle all spoken data and responses per privacy policies and data protection standards.
- **Escalate When Needed:** If an inquiry is too complex or sensitive, suggest that the user connect with a human support representative.
- **Be Brief and Natural:** Aim for responses that are concise and easy to follow, suitable for voice interaction."""

@cl.on_chat_start
async def start():
    await cl.Message(
        content="Hi, Welcome to ShopMe. How can I help you?. Press `P` to talk!"
    ).send()
    await setup_openai_realtime(system_prompt=system_prompt + "\n\n Customer ID: 12121")

@cl.on_message
async def on_message(message: cl.Message):
    openai_realtime: RealtimeClient = cl.user_session.get("openai_realtime")
    if openai_realtime and openai_realtime.is_connected():
        await openai_realtime.send_user_message_content([{ "type": 'input_text', "text": message.content}])
    else:
        await cl.Message(content="Please activate voice mode before sending messages!").send()

@cl.on_audio_start
async def on_audio_start():
    try:
        openai_realtime: RealtimeClient = cl.user_session.get("openai_realtime")
        # TODO: might want to recreate items to restore context
        # openai_realtime.create_conversation_item(item)
        await openai_realtime.connect()
        logger.info("Connected to OpenAI realtime")
        return True
    except Exception as e:
        await cl.ErrorMessage(content=f"Failed to connect to OpenAI realtime: {e}").send()
        return False

@cl.on_audio_chunk
async def on_audio_chunk(chunk: cl.InputAudioChunk):
    openai_realtime: RealtimeClient = cl.user_session.get("openai_realtime")
    if openai_realtime:            
        if openai_realtime.is_connected():
            await openai_realtime.append_input_audio(chunk.data)
        else:
            logger.info("RealtimeClient is not connected")

@cl.on_audio_end
@cl.on_chat_end
@cl.on_stop
async def on_end():
    openai_realtime: RealtimeClient = cl.user_session.get("openai_realtime")
    if openai_realtime and openai_realtime.is_connected():
        await openai_realtime.disconnect()