import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from main import download_topic

class TestDownloadTopic(unittest.TestCase):
    @patch("main.handle_download", new_callable=AsyncMock)
    @patch("main.user")
    def test_download_topic_media_found(self, mock_user, mock_handle_download):
        # Arrange
        mock_bot = MagicMock()
        mock_message = MagicMock()
        mock_message.command = ["/dltopic", "https://t.me/c/12345/67890/1"]
        mock_message.reply = AsyncMock()

        # Mocking discussion history
        history = [
            # Message in the topic with media
            MagicMock(media=True, link="https://t.me/c/12345/67890/2"),
            # Message in the topic without media
            MagicMock(media=False, link="https://t.me/c/12345/67890/3"),
            # Another message in the topic with media
            MagicMock(media=True, link="https://t.me/c/12345/67890/5"),
        ]

        async def async_generator():
            for item in history:
                yield item

        mock_user.get_discussion_history.return_value = async_generator()

        # Act
        asyncio.run(download_topic(mock_bot, mock_message))

        # Assert
        self.assertEqual(mock_handle_download.call_count, 2)
        mock_handle_download.assert_any_call(mock_bot, mock_message, "https://t.me/c/12345/67890/2")
        mock_handle_download.assert_any_call(mock_bot, mock_message, "https://t.me/c/12345/67890/5")

if __name__ == "__main__":
    unittest.main()