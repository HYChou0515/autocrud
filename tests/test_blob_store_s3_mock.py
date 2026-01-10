import pytest
from unittest.mock import patch
from botocore.exceptions import ClientError
from autocrud.resource_manager.blob_store.s3 import S3BlobStore


class TestS3BlobStoreMock:
    @pytest.fixture
    def mock_boto3_client(self):
        with patch("boto3.client") as mock_client:
            yield mock_client

    def test_init_creates_bucket_on_404(self, mock_boto3_client):
        """Test lines 36-40: Auto-create bucket on 404."""
        # Setup mock to raise 404 on head_bucket
        client_instance = mock_boto3_client.return_value
        client_instance.head_bucket.side_effect = ClientError(
            {"Error": {"Code": "404", "Message": "Not Found"}}, "HeadBucket"
        )

        S3BlobStore(bucket="new-bucket")

        # Verify creating
        client_instance.create_bucket.assert_called_once_with(Bucket="new-bucket")

    def test_init_creates_bucket_on_NoSuchBucket(self, mock_boto3_client):
        """Test lines 36-40: Auto-create bucket on NoSuchBucket."""
        client_instance = mock_boto3_client.return_value
        client_instance.head_bucket.side_effect = ClientError(
            {"Error": {"Code": "NoSuchBucket", "Message": "Not Found"}}, "HeadBucket"
        )

        S3BlobStore(bucket="new-bucket")

        client_instance.create_bucket.assert_called_once_with(Bucket="new-bucket")

    def test_init_raises_other_errors(self, mock_boto3_client):
        """Test lines 41-42: Raise other errors."""
        client_instance = mock_boto3_client.return_value
        client_instance.head_bucket.side_effect = ClientError(
            {"Error": {"Code": "500", "Message": "Internal Error"}}, "HeadBucket"
        )

        with pytest.raises(ClientError) as exc:
            S3BlobStore(bucket="existing-bucket")

        assert exc.value.response["Error"]["Code"] == "500"

    def test_get_raises_client_error(self, mock_boto3_client):
        """Test line 63: Raise other errors in get()."""
        client_instance = mock_boto3_client.return_value
        # Ensure init passes
        client_instance.head_bucket.return_value = {}

        store = S3BlobStore()

        # Mock get_object to raise 500
        client_instance.get_object.side_effect = ClientError(
            {"Error": {"Code": "500", "Message": "Internal Error"}}, "GetObject"
        )

        with pytest.raises(ClientError) as exc:
            store.get("some-id")

        assert exc.value.response["Error"]["Code"] == "500"

    def test_exists_ignores_404(self, mock_boto3_client):
        """Test lines 74-75: Return False on 404."""
        client_instance = mock_boto3_client.return_value
        client_instance.head_bucket.return_value = {}

        store = S3BlobStore()

        client_instance.head_object.side_effect = ClientError(
            {"Error": {"Code": "404", "Message": "Not Found"}}, "HeadObject"
        )

        assert store.exists("missing-id") is False

    def test_exists_ignores_NoSuchKey(self, mock_boto3_client):
        """Test lines 74-75: Return False on NoSuchKey."""
        client_instance = mock_boto3_client.return_value
        client_instance.head_bucket.return_value = {}

        store = S3BlobStore()

        client_instance.head_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "Not Found"}}, "HeadObject"
        )

        assert store.exists("missing-id") is False

    def test_exists_raises_other_errors(self, mock_boto3_client):
        """Test line 76: Raise other errors in exists()."""
        client_instance = mock_boto3_client.return_value
        client_instance.head_bucket.return_value = {}

        store = S3BlobStore()

        client_instance.head_object.side_effect = ClientError(
            {"Error": {"Code": "500", "Message": "Internal Error"}}, "HeadObject"
        )

        with pytest.raises(ClientError) as exc:
            store.exists("some-id")

        assert exc.value.response["Error"]["Code"] == "500"
