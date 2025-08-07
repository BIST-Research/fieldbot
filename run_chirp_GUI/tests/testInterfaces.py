import unittest
from unittest.mock import MagicMock, patch, call
import numpy as np
from run_chirp_GUI.src.DataSources import (
    SerialDataSource,
    FileDataSource,
    OP_AMP_START,
    OP_AMP_STOP,
    OP_GET_CHIRP,
    OP_START_JOB,
    DO_CHIRP,
    DONT_CHIRP,
    N_SAMPLES
)

# =============== TEST SERIAL DATA SOURCE ===============
class TestSerialDataSource(unittest.TestCase):
    def setUp(self):
        self.mock_serial = MagicMock()
        self.chirp_bytes = b'\x01\x02\x03'
        self.port = '/dev/ttyUSB0'
        self.data_source = SerialDataSource(self.port, self.chirp_bytes)
        
        # Patch serial module
        serial_patcher = patch('serial.Serial', return_value=self.mock_serial)
        self.mock_serial_class = serial_patcher.start()
        self.addCleanup(serial_patcher.stop)

    def test_prepare_initializes_serial(self):
        # Act
        self.data_source.start()
        
        # Assert
        self.mock_serial_class.assert_called_once_with(self.port, 115200, timeout=2)
        self.mock_serial.write.assert_has_calls([
            call([OP_AMP_START]),
            call([OP_GET_CHIRP]),
            call(self.chirp_bytes),
            call([OP_START_JOB, DONT_CHIRP])
        ])
        self.assertEqual(self.mock_serial.read.call_count, 2)
        self.mock_serial.read.assert_called_with(2 * N_SAMPLES)

    def test_readOnce_sends_command_and_returns_data(self):
        # Setup
        self.data_source.start()
        self.mock_serial.read.side_effect = [
            b'discard',  # First read
            b'valid_data'  # Second read (returned value)
        ]
        
        # Act
        result = self.data_source.next()
        
        # Assert
        self.mock_serial.write.assert_called_with([OP_START_JOB, DO_CHIRP])
        self.assertEqual(result, b'valid_data')

    def test_close_stops_amp_and_closes(self):
        # Setup
        self.data_source.start()
        
        # Act
        self.data_source.close()
        
        # Assert
        self.mock_serial.write.assert_called_with([OP_AMP_STOP])
        self.mock_serial.close.assert_called_once()

    def test_close_handles_closed_serial(self):
        # Setup
        self.data_source.serial = None  # Simulate no serial connection
        
        # Act & Assert (should not raise)
        self.data_source.close()


# =============== TEST FILE DATA SOURCE ===============
class TestFileDataSource(unittest.TestCase):
    def setUp(self):
        self.test_dir = '/test/directory'
        self.data_source = FileDataSource(self.test_dir)
        self.mock_files = ['file1.npy', 'file2.npy', 'file3.npy']

    @patch('os.listdir')
    @patch('os.path.join')
    def test_prepare_loads_npy_files(self, mock_join, mock_listdir):
        # Setup
        mock_listdir.return_value = self.mock_files
        mock_join.side_effect = lambda dir, f: f"{dir}/{f}"
        
        # Act
        self.data_source.start()
        
        # Assert
        mock_listdir.assert_called_once_with(self.test_dir)
        self.assertEqual(self.data_source.paths, [
            '/test/directory/file1.npy',
            '/test/directory/file2.npy',
            '/test/directory/file3.npy'
        ])
        self.assertEqual(self.data_source.index, 0)

    def test_readOnce_handles_empty_directory(self):
        # Setup
        self.data_source.paths = []
        
        # Act
        result = self.data_source.next()
        
        # Assert
        self.assertEqual(result, b"")

    def test_close_is_noop(self):
        # Should not raise any errors
        self.data_source.close()


if __name__ == '__main__':
    unittest.main()