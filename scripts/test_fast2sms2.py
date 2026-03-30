import requests

def send_q_otp(phone, otp):
    url = "https://www.fast2sms.com/dev/bulkV2"
    querystring = {
        "authorization": "XAxFQNGBCwvysn0PcOW93a8T547IjomhfepMHqDbtVzJUR2u1kQMAELIq5BjZ6Urs9PSalzb7mX1V20y",
        "message": "Your Catrin Boys Staff Application OTP is {#var#}. Do not share this with anyone.",
        "variables_values": str(otp),
        "route": "q",
        "numbers": str(phone)
    }
    headers = {'cache-control': "no-cache"}
    response = requests.request("GET", url, headers=headers, params=querystring)
    print("Status:", response.status_code)
    print("Body:", response.text)

send_q_otp("9778106863", "1234")
