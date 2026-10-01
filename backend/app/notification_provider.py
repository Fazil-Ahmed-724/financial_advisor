import json,os,urllib.request,urllib.error

class ProviderTemporaryError(Exception):pass
class ProviderPermanentError(Exception):pass
class ExpoProvider:
    send_url="https://exp.host/--/api/v2/push/send";receipt_url="https://exp.host/--/api/v2/push/getReceipts"
    def _post(self,url,payload):
        headers={"Content-Type":"application/json","Accept":"application/json"};access=os.environ.get("EXPO_ACCESS_TOKEN")
        if access:headers["Authorization"]=f"Bearer {access}"
        request=urllib.request.Request(url,data=json.dumps(payload).encode(),headers=headers,method="POST")
        try:
            with urllib.request.urlopen(request,timeout=float(os.environ.get("NOTIFICATION_PROVIDER_TIMEOUT_SECONDS","10"))) as response:return json.loads(response.read(65536))
        except urllib.error.HTTPError as exc:
            if exc.code==429 or exc.code>=500:raise ProviderTemporaryError("provider temporarily unavailable") from None
            raise ProviderPermanentError("provider rejected request") from None
        except (TimeoutError,urllib.error.URLError,json.JSONDecodeError):raise ProviderTemporaryError("provider temporarily unavailable") from None
    def send(self,payload):return self._post(self.send_url,payload)
    def receipts(self,ids):return self._post(self.receipt_url,{"ids":ids})
