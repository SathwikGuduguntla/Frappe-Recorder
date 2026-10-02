// Runs the writing model (WebLLM) in a background thread so the page stays responsive.
import { WebWorkerMLCEngineHandler } from '@mlc-ai/web-llm'

const handler = new WebWorkerMLCEngineHandler()
self.onmessage = (message) => handler.onmessage(message)
