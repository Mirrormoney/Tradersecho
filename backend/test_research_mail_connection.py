from unittest.mock import MagicMock,patch
import pytest
from . import research as r

def test_transient_connect_recovers_before_processing():
 mailbox=MagicMock();mailbox.select.return_value=('OK',[]);sleep=MagicMock()
 with patch.object(r.imaplib,'IMAP4_SSL',side_effect=[TimeoutError('private detail'),mailbox]) as factory:
  assert r.connect_mailbox('secret',sleep) is mailbox
  assert factory.call_count==2
  sleep.assert_called_once_with(2)
  mailbox.login.assert_called_once()
  mailbox.select.assert_called_once_with('INBOX',readonly=True)

def test_authentication_failure_is_not_retried_or_logged(caplog):
 mailbox=MagicMock();mailbox.login.side_effect=r.imaplib.IMAP4.error('secret credential');sleep=MagicMock()
 with patch.object(r.imaplib,'IMAP4_SSL',return_value=mailbox) as factory:
  with pytest.raises(r.MailboxConnectionError) as error:r.connect_mailbox('secret',sleep)
 assert error.value.stage=='login'
 assert factory.call_count==1
 sleep.assert_not_called();mailbox.shutdown.assert_called_once()
 assert 'secret credential' not in caplog.text

def test_retries_are_bounded():
 with patch.object(r.imaplib,'IMAP4_SSL',side_effect=TimeoutError()) as factory:
  with pytest.raises(r.MailboxConnectionError) as error:r.connect_mailbox('secret',MagicMock())
 assert factory.call_count==2
 assert error.value.stage=='connect'
 assert error.value.error_type=='TimeoutError'

def test_disconnect_during_login_closes_old_connection():
 broken=MagicMock();broken.login.side_effect=r.imaplib.IMAP4.abort('disconnect')
 healthy=MagicMock();healthy.select.return_value=('OK',[])
 with patch.object(r.imaplib,'IMAP4_SSL',side_effect=[broken,healthy]):
  assert r.connect_mailbox('secret',MagicMock()) is healthy
 broken.shutdown.assert_called_once()
