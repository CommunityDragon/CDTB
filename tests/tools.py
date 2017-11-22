import requests

def count_calls(f):
    """Decorator to count calls to a function"""
    def wrapper(*a, **kw):
        wrapper.ncalls += 1
        return f(*a, **kw)
    wrapper.ncalls = 0
    return wrapper

def mock_response(content=None, status_code=200):
    r = requests.Response()
    r.status_code = status_code
    r._content = content
    return r

