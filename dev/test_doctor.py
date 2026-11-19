"""Rootless checks: python3 -m unittest discover -s dev -p test_doctor.py"""
import importlib.machinery
import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

loader = importlib.machinery.SourceFileLoader('doctor', str(Path(__file__).with_name('doctor')))
spec = importlib.util.spec_from_loader(loader.name, loader)
doctor = importlib.util.module_from_spec(spec)
loader.exec_module(doctor)


class DoctorTest(unittest.TestCase):
    def test_wrong_rm_minor_is_reported(self):
        wanted = 'lxc.mount.entry = /dev/nvidia1 dev/nvidia1 none bind,create=file 0 0'
        stale = wanted.replace('nvidia1', 'nvidia0')
        errors = doctor.mount_errors(wanted, stale)
        self.assertTrue(any('missing:' in e for e in errors))
        self.assertTrue(any('stale GPU:' in e for e in errors))
        self.assertTrue(doctor.mount_errors(wanted, wanted + '\n' + stale))
        self.assertEqual(doctor.mount_errors(wanted, wanted), [])

    def test_render_entry_is_owned_by_upstream_generator(self):
        render = 'lxc.mount.entry = /dev/dri/renderD128 dev/dri/renderD128 none bind 0 0'
        self.assertEqual(doctor.mount_errors(render, render.replace('bind', 'bind,optional')), [])

    def test_mount_order_matters(self):
        directory = 'lxc.mount.entry = /root vendor_extra none rbind 0 0'
        file = 'lxc.mount.entry = /lib vendor_extra/lib.so none bind 0 0'
        self.assertTrue(doctor.mount_errors(directory + '\n' + file, file + '\n' + directory))

    def test_dbus_failure_never_kills(self):
        result = subprocess.CompletedProcess([], 1, 'Access denied')
        with patch.object(doctor, 'run', return_value=result), patch.object(doctor, 'root') as root:
            with self.assertRaises(RuntimeError):
                doctor.stop_manual_manager()
            root.assert_not_called()

    def test_fix_requires_desktop_before_mutation(self):
        with patch.dict('os.environ', {}, clear=True), patch.object(doctor, 'root') as root:
            with self.assertRaises(RuntimeError):
                doctor.repair()
            root.assert_not_called()


if __name__ == '__main__':
    unittest.main()
