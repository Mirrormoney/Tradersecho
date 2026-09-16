"""Local operator command. Creates an email-bound invitation, never a password."""
import argparse
from pathlib import Path
from .community import create_owner_invite

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--email', required=True)
    parser.add_argument('--output', required=True, help='Private file outside the repository')
    args = parser.parse_args()
    destination = Path(args.output).resolve()
    if destination.is_relative_to(Path(__file__).resolve().parents[1]):
        parser.error('Save the private invitation outside the project directory.')
    code = create_owner_invite(args.email)
    destination.write_text(
        'PRIVATE — Tradersecho owner setup\n\n'
        'Open http://127.0.0.1:8000 and choose Owner setup at the bottom of the landing page.\n'
        'If already signed in, use My account → I have an owner invitation.\n\n'
        f'Reserved email: {args.email.strip().lower()}\n'
        f'Single-use code: {code}\n\n'
        'Choose your own password privately on the website. This code expires in 72 hours.\n'
        'Claiming it grants Owner and Premium access. Ordinary signup does not grant admin access.\n'
        'Keep this file private and delete it after claiming. A new invitation invalidates an unused old one.\n',
        encoding='utf-8')
    print('Private owner invitation saved. No password has been created.')
