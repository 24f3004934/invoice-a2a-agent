"""Local synthetic A2A lifecycle test. No real payments are made."""

import os
import uuid
import json
import httpx
from dotenv import load_dotenv

load_dotenv(".env")

BASE = os.getenv(
    "TEST_A2A_BASE",
    "http://127.0.0.1:8000/a2a"
).rstrip("/")

OWNER = "Bearer local-lifecycle-owner"
OUTSIDER = "Bearer local-lifecycle-outsider"

HEADERS = {
    "Authorization": OWNER,
    "A2A-Version": "1.0",
    "Content-Type": "application/a2a+json"
}

OTHER = {
    **HEADERS,
    "Authorization": OUTSIDER
}

uid = uuid.uuid4().hex[:12]

batch_id = "test-batch-" + uid
package_id = "test-package-" + uid
message_id = "test-message-" + uid

# Synthetic invoice package
package = {
    "packageId": package_id,
    "documents": [
        {
            "documentType": "invoice",
            "text": (
                "Acme Office Supplies issued invoice "
                "INV-TEST-104 for INR 1,250.00. "
                "The vendor and invoice number are "
                "confirmed [INV-104-A]. "
                "The purchase order matches the delivered "
                "goods and amount [PO-104-B]. "
                "The finance policy confirms this reconciled "
                "invoice is below the INR 5,000 autonomous "
                "payment limit and has not been paid "
                "[POL-104-C]."
            )
        }
    ]
}

initial = {
    "message": {
        "messageId": message_id,
        "role": "ROLE_USER",
        "parts": [
            {
                "mediaType":
                    "application/vnd.ga5.invoice-claim-batch+json",
                "data": {
                    "batchId": batch_id,
                    "policyRevision": "local-test-v1",
                    "packages": [package]
                }
            }
        ]
    },
    "configuration": {
        "returnImmediately": False,
        "historyLength": 20,
        "acceptedOutputModes": [
            "application/vnd.ga5.invoice-action-proposals+json",
            "application/vnd.ga5.invoice-action-receipts+json"
        ]
    }
}


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def show(label, response):
    print(
        f"{label}: HTTP {response.status_code}",
        flush=True
    )

    if response.status_code >= 400:
        print(
            "  Error:",
            response.text[:400],
            flush=True
        )


with httpx.Client(timeout=43) as client:
    # TEST 1: Submit invoice
    response = client.post(
        BASE + "/message:send",
        headers=HEADERS,
        json=initial
    )

    show("INITIAL", response)

    require(
        response.status_code == 200,
        "Initial proposal request failed"
    )

    task = response.json()["task"]

    require(
        task["status"]["state"] == "TASK_STATE_INPUT_REQUIRED",
        "Expected INPUT_REQUIRED"
    )

    require(
        len(task["artifacts"]) == 1,
        "Initial task must have one artifact"
    )

    proposal_part = task["artifacts"][0]["parts"][0]

    require(
        proposal_part["mediaType"] ==
        "application/vnd.ga5.invoice-action-proposals+json",
        "Wrong proposal media type"
    )

    proposals = proposal_part["data"]["proposals"]

    require(
        len(proposals) == 1,
        "Expected exactly one proposal"
    )

    proposal = proposals[0]

    print("\nPROPOSED ACTION:", proposal["action"])
    print(
        "FACTS:",
        json.dumps(
            proposal["facts"],
            ensure_ascii=False
        )
    )
    print("EVIDENCE:", proposal["evidenceRefs"])
    print("RATIONALE:", proposal["rationale"])

    require(
        proposal["action"] == "settle_invoice",
        "Unexpected invoice decision"
    )

    require(
        len(proposal["evidenceRefs"]) == 3,
        "Expected exactly three evidence references"
    )

    tid = task["id"]
    cid = task["contextId"]

    # TEST 2: Cross-user isolation
    outsider = client.get(
        BASE + "/tasks/" + tid,
        headers=OTHER
    )

    show("OUTSIDER READ", outsider)

    require(
        outsider.status_code in (403, 404),
        "Cross-user task disclosure!"
    )

    outsider_list = client.get(
        BASE + "/tasks",
        headers=OTHER
    )

    show("OUTSIDER LIST", outsider_list)

    require(
        outsider_list.status_code == 200
        and not any(
            t.get("id") == tid
            for t in outsider_list.json()["tasks"]
        ),
        "Cross-user list disclosure!"
    )

    # TEST 3: Initial message replay
    replay = client.post(
        BASE + "/message:send",
        headers=HEADERS,
        json={
            **initial,
            "configuration": {
                "returnImmediately": True
            }
        }
    )

    show("INITIAL REPLAY", replay)

    require(
        replay.status_code == 200
        and replay.json()["task"] == task,
        "Initial idempotency failed"
    )

    # TEST 4: Same message ID, changed content
    changed = json.loads(json.dumps(initial))

    changed["message"]["parts"][0]["data"]["batchId"] += (
        "-changed"
    )

    conflict = client.post(
        BASE + "/message:send",
        headers=HEADERS,
        json=changed
    )

    show("MESSAGE ID CONFLICT", conflict)

    require(
        conflict.status_code == 409,
        "Expected 409 for changed message"
    )

    # TEST 5: Send accepted result
    nonce = "local-nonce-" + uuid.uuid4().hex

    result_message = {
        "message": {
            "messageId": "result-" + uid,
            "taskId": tid,
            "contextId": cid,
            "role": "ROLE_USER",
            "parts": [
                {
                    "mediaType":
                        "application/vnd.ga5.invoice-action-results+json",
                    "data": {
                        "batchId": batch_id,
                        "results": [
                            {
                                "packageId": package_id,
                                "actionId": proposal["actionId"],
                                "action": proposal["action"],
                                "outcome": "ACCEPTED",
                                "receiptNonce": nonce
                            }
                        ]
                    }
                }
            ]
        }
    }

    result = client.post(
        BASE + "/message:send",
        headers=HEADERS,
        json=result_message
    )

    show("ACCEPTED RESULT", result)

    require(
        result.status_code == 200,
        "Result continuation failed"
    )

    finished = result.json()["task"]

    require(
        finished["status"]["state"] ==
        "TASK_STATE_COMPLETED",
        "Expected COMPLETED"
    )

    require(
        len(finished["artifacts"]) == 2,
        "Expected proposal and receipt artifacts"
    )

    receipt_part = finished["artifacts"][1]["parts"][0]

    require(
        receipt_part["mediaType"] ==
        "application/vnd.ga5.invoice-action-receipts+json",
        "Wrong receipt media type"
    )

    executions = receipt_part["data"]["executions"]

    require(
        len(executions) == 1
        and executions[0]["receiptNonce"] == nonce,
        "Receipt nonce mismatch"
    )

    require(
        executions[0]["actionId"] == proposal["actionId"],
        "Receipt action ID mismatch"
    )

    require(
        len(finished["history"]) == 2,
        "Expected initial and result messages"
    )

    # TEST 6: Replay accepted result
    final_replay = client.post(
        BASE + "/message:send",
        headers=HEADERS,
        json=result_message
    )

    show("RESULT REPLAY", final_replay)

    require(
        final_replay.status_code == 200
        and final_replay.json()["task"] == finished,
        "Final replay mismatch"
    )

    # TEST 7: Read completed task
    read = client.get(
        BASE + "/tasks/" + tid,
        headers=HEADERS
    )

    show("TERMINAL READ", read)

    require(
        read.status_code == 200
        and read.json() == finished,
        "Persisted terminal task mismatch"
    )

    # TEST 8: Cancel completed task
    cancel = client.post(
        BASE + "/tasks/" + tid + ":cancel",
        headers=HEADERS
    )

    show("CANCEL TERMINAL TASK", cancel)

    require(
        cancel.status_code == 409,
        "Terminal task must not be canceled"
    )

print(
    "\nPASS: local proposal, receipt, idempotency, "
    "isolation, and terminal replay tests."
)

print(
    "NOTE: Concurrent cancellation and hidden audit "
    "accuracy are not tested here."
)
