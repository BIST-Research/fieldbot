import unittest
from unittest.mock import MagicMock, patch, call
from PyQt5.QtCore import QThread, QMutex
from PyQt5.QtTest import QSignalSpy
from run_chirp_GUI.src.DataSources import DataSource

# Import the class to test (adjust import path as needed)
from src.DataWorker import DataWorker

class TestDataWorker(unittest.TestCase):
    def setUp(self):
        # Create worker and mock data source
        self.worker = DataWorker()
        self.mock_source = MagicMock(spec=DataSource)
        
        # Mock the thread to avoid real threading
        self.worker.thread = MagicMock(spec=QThread)
        self.worker.thread.isRunning.return_value = False
        
        # Track worker state
        self.worker.running = False
        self.worker.paused = True

    def tearDown(self):
        if self.worker.running:
            self.worker.stop()

    def test_initial_state(self):
        """Test initial worker state"""
        self.assertFalse(self.worker.running)
        self.assertTrue(self.worker.paused)
        self.assertIsNone(self.worker.source)
        self.assertIsInstance(self.worker._lock, QMutex)

    def test_load_source(self):
        """Test loading a new data source"""
        # First load
        self.worker.load(self.mock_source)
        self.mock_source.prepare.assert_called_once()
        self.assertEqual(self.worker.source, self.mock_source)
        
        # Replace with new source
        new_source = MagicMock(spec=DataSource)
        self.worker.load(new_source)
        
        # Verify old source was closed
        self.mock_source.close.assert_called_once()
        # Verify new source was prepared
        new_source.prepare.assert_called_once()
        self.assertEqual(self.worker.source, new_source)

    def test_run_once(self):
        """Test single read operation"""
        self.worker.load(self.mock_source)
        test_data = b"test_data"
        self.mock_source.readOnce.return_value = test_data
        
        # Spy on dataReady signal
        spy = QSignalSpy(self.worker.dataReady)
        
        self.worker.next()
        
        # Verify read and signal emission
        self.mock_source.readOnce.assert_called_once()
        self.assertEqual(len(spy), 1)
        self.assertEqual(spy[0][0], test_data)

    def test_run_once_no_source(self):
        """Test runOnce with no data source"""
        spy = QSignalSpy(self.worker.dataReady)
        self.worker.next()
        self.assertEqual(len(spy), 0)  # No signal emitted

    def test_thread_lifecycle(self):
        """Test start/stop thread management"""
        # Start the worker
        self.worker.start()
        self.assertTrue(self.worker.running)
        self.worker.thread.start.assert_called_once()
        
        # Stop the worker
        self.worker.stop()
        self.assertFalse(self.worker.running)
        self.worker.thread.quit.assert_called_once()
        self.worker.thread.wait.assert_called_once_with(500)

    @patch.object(QThread, 'msleep')
    def test_worker_loop(self, mock_msleep):
        """Test the main worker loop behavior"""
        # Setup mock return values
        test_data = b"test_data"
        self.mock_source.readOnce.side_effect = [test_data, b"", test_data, Exception("Break loop")]
        
        # Replace real thread with mock
        self.worker.thread = QThread()
        
        # Start worker
        self.worker.load(self.mock_source)
        self.worker.start()
        self.worker.unpause()
        
        # Spy on signals
        spy = QSignalSpy(self.worker.dataReady)
        
        try:
            # Execute the run loop directly (not in real thread)
            self.worker._run()
        except Exception:
            pass
        
        # Verify expected behavior
        self.assertEqual(len(spy), 2)  # Should get 2 valid data emits
        self.mock_source.readOnce.call_count == 4
        mock_msleep.assert_called_with(10)  # Should sleep on empty data
        
        # Verify pause/resume
        self.worker.pause()
        self.assertTrue(self.worker.paused)
        self.worker.unpause()
        self.assertFalse(self.worker.paused)

    def test_pause_mechanism(self):
        """Test pause/unpause functionality"""
        self.worker.pause()
        self.assertTrue(self.worker.paused)
        
        self.worker.unpause()
        self.assertFalse(self.worker.paused)

    def test_cleanup_on_stop(self):
        """Test resource cleanup when stopping"""
        self.worker.load(self.mock_source)
        self.worker.start()
        self.worker.stop()
        
        # Verify source was closed
        self.mock_source.close.assert_called_once()
        self.assertIsNone(self.worker.source)

    def test_thread_safety(self):
        """Test lock acquisition in public methods"""
        with patch.object(self.worker._lock, 'lock') as mock_lock, \
             patch.object(self.worker._lock, 'unlock') as mock_unlock:
            
            self.worker.load(self.mock_source)
            mock_lock.assert_called_once()
            mock_unlock.assert_called_once()
            
            mock_lock.reset_mock()
            mock_unlock.reset_mock()
            
            self.worker.next()
            mock_lock.assert_called_once()
            mock_unlock.assert_called_once()
            
            mock_lock.reset_mock()
            mock_unlock.reset_mock()
            
            self.worker.stop()
            mock_lock.assert_called_once()
            mock_unlock.assert_called_once()

if __name__ == '__main__':
    unittest.main()