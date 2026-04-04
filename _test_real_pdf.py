import sys
import time
import requests

BASE_URL = "http://127.0.0.1:8000"
PDF_PATH = r"c:\Users\shiva\OneDrive\Desktop\Trikon\ContractGuard\tests\SampleContract-Shuttle (1).pdf"

def main():
    print(f"Uploading PDF: {PDF_PATH}")
    with open(PDF_PATH, "rb") as f:
        resp = requests.post(
            f"{BASE_URL}/upload",
            files={"file": ("SampleContract.pdf", f, "application/pdf")}
        )
    
    if resp.status_code != 200:
        print(f"Upload failed: {resp.status_code} {resp.text}")
        sys.exit(1)
        
    upload_data = resp.json()
    contract_id = upload_data["contract_id"]
    print(f"Upload successful. Contract ID: {contract_id}")
    
    # Wait for processing
    print("Waiting for indexing to complete...")
    for _ in range(120):
        status_resp = requests.get(f"{BASE_URL}/contracts/{contract_id}/status")
        if status_resp.status_code == 200:
            status = status_resp.json()["status"]
            if status == "ready":
                print("Status: READY")
                break
            elif status == "failed":
                print(f"Status failed: {status_resp.json().get('error')}")
                sys.exit(1)
        time.sleep(1)
    else:
        print("Timeout waiting for status ready.")
        sys.exit(1)
        
    # Get Summary
    print("\nFetching Summary...")
    resp = requests.post(f"{BASE_URL}/summary", json={"contract_id": contract_id, "max_chars": 1500})
    if resp.status_code == 200:
        print(resp.json()["summary"])
    else:
        print("Summary error:", resp.text)
        
    # Get Risks
    print("\nFetching Risk Analysis...")
    resp = requests.post(f"{BASE_URL}/risks", json={"contract_id": contract_id})
    if resp.status_code == 200:
        risks_data = resp.json()
        print(f"Safety Score: {risks_data['safety_score']}/100 - {risks_data['risk_level']}")
        for risk in risks_data["risks"]:
            print(f" - [{risk['severity']}] {risk['title']}: {risk['explanation']}")
    else:
        print("Risks error:", resp.text)

if __name__ == "__main__":
    main()
