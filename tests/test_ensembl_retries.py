import requests

from unittest.mock import Mock, patch

from services.ensembl import ensembl_get


def test_retry_after_server_error():

    # First response: temporary server error
    failed_response = Mock()
    failed_response.status_code = 503

    # Second response: successful request
    successful_response = Mock()
    successful_response.status_code = 200
    successful_response.json.return_value = {
        "message": "Success"
    }

    with patch(
        "services.ensembl.requests.get",
        side_effect=[
            failed_response,
            successful_response
        ]
    ) as mock_get:

        # Avoid waiting during the test
        with patch("services.ensembl.time.sleep"):

            response = ensembl_get(
                url="https://rest.ensembl.org/test",
                params={"feature": "gene"}
            )

    print("\nTEST A: RETRY AFTER HTTP 503")

    print(f"API calls: {mock_get.call_count}")
    print(f"Final status: {response.status_code}")

    assert mock_get.call_count == 2
    assert response.status_code == 200

    print("Retry test passed!")


def test_retry_after_timeout():

    # Simulate a successful response
    successful_response = Mock()
    successful_response.status_code = 200

    # First request times out; second succeeds
    with patch(
        "services.ensembl.requests.get",
        side_effect=[
            requests.Timeout("Simulated timeout"),
            successful_response
        ]
    ) as mock_get:

        # Skip actual waiting during the test
        with patch("services.ensembl.time.sleep"):

            response = ensembl_get(
                url="https://rest.ensembl.org/test",
                params={"feature": "gene"}
            )

    print("\nTEST B: RETRY AFTER TIMEOUT")

    print(f"API calls: {mock_get.call_count}")
    print(f"Final status: {response.status_code}")

    assert mock_get.call_count == 2
    assert response.status_code == 200

    print("Timeout recovery test passed!")


if __name__ == "__main__":

    print("\nENSEMBL RETRY TEST")
    print("-" * 60)

    test_retry_after_server_error()
    test_retry_after_timeout()

    print("\nAll Ensembl retry tests passed!")