from fastapi import FastAPI
from utils.telemetry import trace_function


@trace_function
async def fetch_syllabus(app: FastAPI, node_id: str):
    pass
