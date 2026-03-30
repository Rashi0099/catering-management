import requests

def send_fast2sms_otp(phone, otp):
    url = "https://www.fast2sms.com/dev/bulkV2"
    querystring = {
        "authorization": "XAxFQNGBCwvysn0PcOW93a8T547IjomhfepMHqDbtVzJUR2u1kQMAELIq5BjZ6Urs9PSalzb7mX1V20y",
        "variables_values": str(otp),
        "route": "otp",
        "numbers": str(phone)
    }
    headers = {'cache-control': "no-cache"}
    response = requests.request("GET", url, headers=headers, params=querystring)
    print(f"Phone: {phone}")
    print("Status:", response.status_code)
    print("Body:", response.text)
    print("-" * 20)

send_fast2sms_otp("9999999999", "1234")
send_fast2sms_otp("9876543210", "1234")
send_fast2sms_otp("7736637373", "1234") # Random indian number starting with 7
send_fast2sms_otp("8111929292", "1234") # Random indian number starting with 8
