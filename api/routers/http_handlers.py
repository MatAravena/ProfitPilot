from fastapi import APIRouter, HTTPException, status

def default_http_answer(value: True , message = '', status= status.HTTP_200_OK):
    return {value : value, message: message, status: status}
def default_http_error(value: False , message = '', status= status.HTTP_400_BAD_REQUEST):
    return {value : value, message: message, status: status}