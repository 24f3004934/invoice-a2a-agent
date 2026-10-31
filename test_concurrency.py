
"""
Standalone A2A cancel-versus-receipt concurrency test.

Run:
    python test_concurrency.py

Requirements:
    - FastAPI server running on localhost:8000
    - httpx installed
    - Groq and Neon configured in the server
"""

import asyncio
import copy
import uuid

import httpx


BASE = "http://127.0.0.1:8000/a2a"

HEADERS = {
    "Authorization": "Bearer local-concurrency-owner",
    "A2A-Version": "1.0",
    "Content-Type": "application/a2a+json",
}


def make_initial_request():
    unique_id = uuid.uuid4().hex

    return {
        "message": {
            "messageId": "race-message-" + unique_id,
            "role": "ROLE_USER",
            "parts": [
                {
                    "mediaType":
                        "application/vnd.ga5.invoice-claim-batch+json",
                    "data": {
                        "batchId": "race-batch-" + unique_id,
                        "policyRevision": "local-test-v1",
                        "packages": [
                            {
                                "packageId":
                                    "race-package-" + unique_id,
                                "documents": [
                                    {
                                        "documentType": "invoice",
                                        "text": (
                                            "Acme Office Supplies issued "
                                            "invoice INV-TEST-104 for "
                                            "INR 1,250.00. "
                                            "The vendor and invoice number "
                                            "are confirmed [INV-104-A]. "
                                            "The purchase order matches "
                                            "the delivered goods and amount "
                                            "[PO-104-B]. "
                                            "Finance policy confirms this "
                                            "reconciled invoice is below "
                                            "the INR 5,000 autonomous "
                                            "payment limit and has not "
                                            "been paid [POL-104-C]."
                                        ),
                                    }
                                ],
                            }
                        ],
                    },
                }
            ],
        },
        "configuration": {
            "returnImmediately": False,
            "historyLength": 20,
            "acceptedOutputModes": [
                "application/vnd.ga5.invoice-action-proposals+json",
                "application/vnd.ga5.invoice-action-receipts+json",
            ],
        },
    }


async def run_race(client, run_number):
    print(f"\n========== RACE {run_number} ==========")

    # 1. Create a fresh invoice task.
    initial = make_initial_request()

    response = await client.post(
        BASE + "/message:send",
        headers=HEADERS,
        json=initial,
    )

    print("CREATE:", response.status_code)

    assert response.status_code == 200, response.text

    task = response.json()["task"]

    assert (
        task["status"]["state"]
        == "TASK_STATE_INPUT_REQUIRED"
    ), "Task should be INPUT_REQUIRED"

    task_id = task["id"]
    context_id = task["contextId"]

    proposal = (
        task["artifacts"][0]["parts"][0]
        ["data"]["proposals"][0]
    )

    data = initial["message"]["parts"][0]["data"]

    # 2. Prepare accepted result with a unique receipt nonce.
    receipt_nonce = "nonce-" + uuid.uuid4().hex

    result_request = {
        "message": {
            "messageId": "result-" + uuid.uuid4().hex,
            "taskId": task_id,
            "contextId": context_id,
            "role": "ROLE_USER",
            "parts": [
                {
                    "mediaType":
                        "application/vnd.ga5.invoice-action-results+json",
                    "data": {
                        "batchId": data["batchId"],
                        "results": [
                            {
                                "packageId":
                                    data["packages"][0]["packageId"],
                                "actionId": proposal["actionId"],
                                "action": proposal["action"],
                                "outcome": "ACCEPTED",
                                "receiptNonce": receipt_nonce,
                            }
                        ],
                    },
                }
            ],
        }
    }

    # 3. Launch receipt submission and cancellation together.
    async def send_result():
        return await client.post(
            BASE + "/message:send",
            headers=HEADERS,
            json=result_request,
        )

    async def cancel_task():
        return await client.post(
            BASE + "/tasks/" + task_id + ":cancel",
            headers=HEADERS,
        )

    result_response, cancel_response = await asyncio.gather(
        send_result(),
        cancel_task(),
    )

    print("RESULT:", result_response.status_code)
    print("CANCEL:", cancel_response.status_code)

    if result_response.status_code != 200:
        print(
            "RESULT ERROR:",
            result_response.text[:500],
        )

    if cancel_response.status_code != 200:
        print(
            "CANCEL ERROR:",
            cancel_response.text[:500],
        )

    # 4. Retrieve final task state.
    final_response = await client.get(
        BASE + "/tasks/" + task_id,
        headers=HEADERS,
    )

    assert final_response.status_code == 200, (
        final_response.text
    )

    final_task = final_response.json()
    final_state = final_task["status"]["state"]

    print("FINAL STATE:", final_state)

    # 5. Exactly one operation must win.
    statuses = sorted([
        result_response.status_code,
        cancel_response.status_code,
    ])

    assert statuses == [200, 409], (
        f"Expected one 200 and one 409, got {statuses}"
    )

    if result_response.status_code == 200:
        assert final_state == "TASK_STATE_COMPLETED", (
            "Receipt won but task is not COMPLETED"
        )

        artifacts = final_task.get("artifacts", [])

        assert len(artifacts) == 2, (
            "Completed task should contain "
            "proposal and receipt artifacts"
        )

        executions = (
            artifacts[1]["parts"][0]["data"]["executions"]
        )

        assert len(executions) == 1, (
            "Expected exactly one receipt execution"
        )

        assert (
            executions[0]["receiptNonce"] == receipt_nonce
        ), "Receipt nonce mismatch"

        print("WINNER: RECEIPT")

    else:
        assert cancel_response.status_code == 200

        assert final_state == "TASK_STATE_CANCELED", (
            "Cancellation won but task is not CANCELED"
        )

        print("WINNER: CANCELLATION")

    print(f"PASS: Race {run_number}")


async def main():
    # Start with 3 independent races.
    # Each race creates a new invoice task.
    total_runs = 3

    async with httpx.AsyncClient(timeout=60) as client:
        for run_number in range(1, total_runs + 1):
            await run_race(client, run_number)

    print("\n===================================")
    print(f"PASS: All {total_runs} concurrency tests passed.")
    print("No task was both completed and canceled.")
    print("===================================")


if __name__ == "__main__":
    asyncio.run(main())
