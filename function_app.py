import os
import azure.functions as func
import json
import logging
import traceback
import base64
from parser import generate_openapi_schema
from dataclasses import dataclass

@dataclass
class RequestBody:
    version: str
    revision: str
    contents: dict[str, str]

app = func.FunctionApp()

@app.function_name(name="apigen")
@app.route(route="createSchema/{version}/{revision}", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
@app.blob_output(
    arg_name="outputblob",
    path="api-specs/{version}-{revision}",
    connection=os.getenv("AzureWebJobsStorage")
)
def createSchema(req: func.HttpRequest, outputblob: func.Out[str], version: str, revision:str) -> func.HttpResponse:
    try:
        data = req.get_json()
        req_body = RequestBody(**data)
    except ValueError as e:
        return func.HttpResponse(f"Invalid JSON: {str(e)}", status_code=400)
    except TypeError as e:
        return func.HttpResponse(f"Missing required field: {str(e)}", status_code=400)
    else:
        contents = req_body.contents

        specs = {}
        for key, encoded_content in contents.items():
            try:
                decoded_bytes = base64.b64decode(encoded_content)
                decoded_hcl = decoded_bytes.decode('utf-8')
                
                spec = generate_openapi_schema(decoded_hcl)
                specs[key] = spec
            except UnicodeDecodeError as e:
                logging.error(f"Base64 decoding failed for {key}: {str(e)}")
                return func.HttpResponse(f"Invalid base64 encoding in {key}", status_code=400)
            except Exception as e:
                logging.error(f"Processing failed for {key}: {str(e)}")
                logging.error(traceback.format_exc())
                return func.HttpResponse(f"Error processing {key}: {str(e)}", status_code=400)            

        api_spec = {
            "openapi": "3.0.0", 
            "info": {
                "title": "Request Subscription API",
                "version": revision
            },
            "paths": {
                "/requestSubscription": {
                    "post": {
                        "summary": "Request a subscription",
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": specs
                                }
                            }
                        },
                        "responses": {
                            "201": {
                                "description": "Subscription requested successfully"
                            }
                        }
                    }
                }
            }
        }
        outputblob.set(json.dumps(api_spec))
    
        return func.HttpResponse(
            f"Blob created successfully!",
            status_code=201
        )

