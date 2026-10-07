"""Bounded requests to Bloomberg's API field-definition service."""
import time


class FieldService:
    def __init__(self, host="localhost", port=8194, timeout_seconds=20):
        self.host, self.port, self.timeout_seconds = host, port, timeout_seconds

    def request(self, kind, *, query=None, fields=None):
        import blpapi
        options = blpapi.SessionOptions()
        options.setServerHost(self.host)
        options.setServerPort(self.port)
        options.setConnectTimeout(int(self.timeout_seconds * 1000))
        session = blpapi.Session(options)
        try:
            if not session.start() or not session.openService("//blp/apiflds"):
                raise RuntimeError("Unable to open Bloomberg API field service.")
            request = session.getService("//blp/apiflds").createRequest(kind)
            request.set("returnFieldDocumentation", True)
            if kind == "FieldSearchRequest":
                if not query:
                    raise ValueError("A field search needs a query.")
                request.set("searchSpec", query)
            elif kind == "FieldInfoRequest":
                if not fields:
                    raise ValueError("Field information needs explicit identifiers.")
                for field in fields:
                    request.getElement("id").appendValue(field)
            else:
                raise ValueError("Unsupported field-service request.")
            session.sendRequest(request)
            deadline = time.monotonic() + self.timeout_seconds
            responses = []
            while time.monotonic() < deadline:
                event = session.nextEvent(500)
                for message in event:
                    if event.eventType() in {blpapi.Event.RESPONSE, blpapi.Event.PARTIAL_RESPONSE}:
                        result = message.asElement().toPy()
                        if "responseError" in result:
                            raise RuntimeError(str(result["responseError"]))
                        responses.append(result)
                    elif event.eventType() == blpapi.Event.REQUEST_STATUS:
                        raise RuntimeError(str(message))
                    elif str(message.messageType()) == "SessionTerminated":
                        raise RuntimeError("Bloomberg field session terminated.")
                if event.eventType() == blpapi.Event.RESPONSE:
                    return responses
            raise TimeoutError(f"Bloomberg {kind} timed out after {self.timeout_seconds} seconds.")
        finally:
            session.stop()

    def search(self, query):
        return self.request("FieldSearchRequest", query=query)

    def info(self, fields):
        return self.request("FieldInfoRequest", fields=fields)
