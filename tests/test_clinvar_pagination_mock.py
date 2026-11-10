from unittest.mock import patch, Mock

from services.clinvar import search_clinvar_region


def make_mock_response(ids, total_count):
    """Create a simulated NCBI ESearch response."""

    response = Mock()

    response.json.return_value = {
        "esearchresult": {
            "count": str(total_count),
            "idlist": ids,
        }
    }

    return response


def test_multiple_pages():

    # Simulate 250 ClinVar records
    all_ids = [str(i) for i in range(1, 251)]

    # Simulate three API responses
    mock_responses = [
        make_mock_response(all_ids[0:100], 250),
        make_mock_response(all_ids[100:200], 250),
        make_mock_response(all_ids[200:250], 250),
    ]

    with patch(
        "services.clinvar.ncbi_get",
        side_effect=mock_responses
    ) as mock_get:

        # Skip the delays between simulated requests
        with patch("services.clinvar.time.sleep"):

            result = search_clinvar_region(
                chrom="chr1",
                start=100,
                end=200,
                max_records=1000
            )

    print("\nTEST A: MULTIPLE PAGES")
    print(f"Total records: {result['total_count']}")
    print(f"Retrieved IDs: {len(result['variant_ids'])}")
    print(f"API calls: {mock_get.call_count}")
    print(f"Truncated: {result['truncated']}")

    assert result["total_count"] == 250
    assert len(result["variant_ids"]) == 250
    assert result["variant_ids"] == all_ids
    assert mock_get.call_count == 3
    assert result["truncated"] is False

    # Verify that each request starts at the correct position
    requested_offsets = [
        call.args[1]["retstart"]
        for call in mock_get.call_args_list
    ]

    assert requested_offsets == [0, 100, 200]

    print("Multiple-page retrieval passed!")


def test_retrieval_limit():

    # Simulate 250 records, but retrieve only 150
    all_ids = [str(i) for i in range(1, 251)]

    mock_responses = [
        make_mock_response(all_ids[0:100], 250),
        make_mock_response(all_ids[100:150], 250),
    ]

    with patch(
        "services.clinvar.ncbi_get",
        side_effect=mock_responses
    ) as mock_get:

        with patch("services.clinvar.time.sleep"):

            result = search_clinvar_region(
                chrom="chr1",
                start=100,
                end=200,
                max_records=150
            )

    print("\nTEST B: RETRIEVAL LIMIT")
    print(f"Total records: {result['total_count']}")
    print(f"Retrieved IDs: {len(result['variant_ids'])}")
    print(f"API calls: {mock_get.call_count}")
    print(f"Truncated: {result['truncated']}")

    assert result["total_count"] == 250
    assert len(result["variant_ids"]) == 150
    assert mock_get.call_count == 2
    assert result["truncated"] is True

    requested_page_sizes = [
        call.args[1]["retmax"]
        for call in mock_get.call_args_list
    ]

    assert requested_page_sizes == [100, 50]

    print("Retrieval limit passed!")


if __name__ == "__main__":

    print("\nCLINVAR MOCK PAGINATION TEST")
    print("-" * 60)

    test_multiple_pages()
    test_retrieval_limit()

    print("\nAll mock pagination tests passed!")