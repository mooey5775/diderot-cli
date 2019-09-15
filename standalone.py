import requests
from importlib import util
import importlib
import argparse
import shlex
import os

from pathlib import Path

from api_calls import DiderotAPIInterface, exit_with_error

import sys
assert sys.version_info >= (3, 6), 'Python3.6 is required'


# Custom formatter for argparse which displays all positional arguments first.
class Formatter(argparse.HelpFormatter):
    # use defined argument order to display usage
    def _format_usage(self, usage, actions, groups, prefix):
        if prefix is None:
            prefix = 'usage: '

        # if usage is specified, use that
        if usage is not None:
            usage = usage % dict(prog=self._prog)

        # if no optionals or positionals are available, usage is just prog
        elif usage is None and not actions:
            usage = '%(prog)s' % dict(prog=self._prog)
        elif usage is None:
            prog = '%(prog)s' % dict(prog=self._prog)
            # build full usage string
            action_usage = self._format_actions_usage(actions, groups)  # NEW
            usage = ' '.join([s for s in [prog, action_usage] if s])
            # omit the long line wrapping code
        # prefix with 'usage:'
        return '%s%s\n\n' % (prefix, usage)


DEFAULT_CRED_LOCATIONS = [
    '~/private/.diderot/credentials', '~/.diderot/credentials']


# Command line argument generator for the CLI.
# Returns a parser that can be extended with additional commands.
class DiderotCLIArgs(object):
    # Generate a base parser object for use by both the user and admin CLI's.
    @staticmethod
    def generate_parser(prog, desc):
        parser = argparse.ArgumentParser(
            prog=prog, description=desc, formatter_class=Formatter)
        # Basic arguments not tied to a particular CLI version.
        parser.add_argument("--url", default="https://www.diderot.one")
        parser.add_argument("--username", default=None)
        parser.add_argument("--password", default=None)
        parser.add_argument("--credentials", default=None,
                            help="Read credentials from a credientials file. \
                                  The credential file format is a text file with the \
                                  username on the first line and the password on the second.")
        return parser

    # Generate a parser for the user CLI.
    @staticmethod
    def generate_user_parser(prog, desc):
        parser = DiderotCLIArgs.generate_parser(prog, desc)
        subparsers = parser.add_subparsers(
            title="command", help="Different commands.", dest="command")
        subparsers.required = True

        # subparser for list_assignments
        list_assignments = subparsers.add_parser(
            "list_assignments", help="List all assignments in a course.", formatter_class=Formatter)
        list_assignments.add_argument(
            "course", help="Course to list assignments of.")

        # subparser for list_courses
        list_courses = subparsers.add_parser(
            "list_courses", help="List all courses.", formatter_class=Formatter)

        # subparser for submit_assignment
        submit_assignment = subparsers.add_parser(
            "submit_assignment", help="Submit handin to assignment.", formatter_class=Formatter)
        submit_assignment.add_argument(
            "course", help="Course to submit assignment to.")
        submit_assignment.add_argument(
            "homework", help="Homework to submit to.")
        submit_assignment.add_argument(
            "handin_path", help="Path to handin file.")

        # subparser for download_assignment
        download_assignment = subparsers.add_parser(
            "download_assignment", help="Download homework handout files.", formatter_class=Formatter)
        download_assignment.add_argument(
            "course", help="Course to download assignment from.")
        download_assignment.add_argument(
            "homework", help="Homework assignment to download.")

        return parser, subparsers

    # Generate a parser for the admin CLI.
    @staticmethod
    def generate_admin_parser(prog, desc):
        parser, subparsers = DiderotCLIArgs.generate_user_parser(prog, desc)

        # subparser for create_chapter
        create_chapter = subparsers.add_parser(
            "create_chapter", help="Create a chapter in a book.", formatter_class=Formatter)
        create_chapter.add_argument(
            "course", help="Course that the book belongs to.")
        create_chapter.add_argument(
            "book", help="Book to create a chapter within.")
        create_chapter.add_argument(
            "--part", help="Part number that the chapter belong within. \
                            This is not needed if the book is a booklet.")
        create_chapter.add_argument(
            "--number", help="Number of the new chapter.", required=True)
        create_chapter.add_argument(
            "--title", help="Optional title of new chapter (default = Chapter)", default=None)
        create_chapter.add_argument(
            "--label", help="Optional label of new chapter (default= randomly generated)", default=None)

        create_part = subparsers.add_parser(
            "create_part", help="Create a part in a book", formatter_class=Formatter)
        create_part.add_argument(
            "course", help="Course that the book belongs to.")
        create_part.add_argument("book", help="Book to create part in.")
        create_part.add_argument("title", help="Title of the new part.")
        create_part.add_argument("number", help="Number of the new part.")
        create_part.add_argument(
            "--label", help="Label for the new part (default = random).", default=None)

        # subparsers for release/unrelease chapter
        release_chapter = subparsers.add_parser(
            "release_chapter", help="Release a book chapter", formatter_class=Formatter)
        release_chapter.add_argument(
            "course", help="Course to release chapter in.")
        release_chapter.add_argument(
            "book", help="Book that the chapter belongs to.")
        chapter_id_group = release_chapter.add_mutually_exclusive_group(
            required=True)
        chapter_id_group.add_argument(
            '--chapter_number', default=None, help="Number of chapter to release.")
        chapter_id_group.add_argument(
            '--chapter_label', default=None, help="Label of chapter to release.")

        unrelease_chapter = subparsers.add_parser(
            "unrelease_chapter", help="Unrelease a book chapter", formatter_class=Formatter)
        unrelease_chapter.add_argument(
            "course", help="Course to unrelease chapter in.")
        unrelease_chapter.add_argument(
            "book", help="Book that the chapter belongs to.")
        chapter_id_group = unrelease_chapter.add_mutually_exclusive_group(
            required=True)
        chapter_id_group.add_argument(
            '--chapter_number', default=None, help="Number of chapter to unrelease.")
        chapter_id_group.add_argument(
            '--chapter_label', default=None, help="Label of chapter to unrelease.")

        # subparser for list_books
        list_books = subparsers.add_parser(
            "list_books", help="List all books.", formatter_class=Formatter)
        list_books.add_argument(
            "course", help="Course label to filter book results by.", default=None, nargs="?")
        list_books.add_argument("--all", action="store_true",
                                help="Optional flag to show all books visible to user.")

        # subparser for list_chapters
        list_chapters = subparsers.add_parser(
            "list_chapters", help="List all chapters in a book.", formatter_class=Formatter)
        list_chapters.add_argument(
            "course", help="Course that the book belongs to.")
        list_chapters.add_argument("book", help="Book to list chapters of.")
        # TODO (rohany): add a filter by parts here.

        # subparser for list_parts
        list_parts = subparsers.add_parser(
            "list_parts", help="List all parts of a book.", formatter_class=Formatter)
        list_parts.add_argument(
            "course", help="Course that the book belongs to.")
        list_parts.add_argument("book", help="Book to list parts of.")

        # subparser for update_assignment
        update_assignment = subparsers.add_parser(
            "update_assignment", help="Update the files linked to an assignment.", formatter_class=Formatter)
        update_assignment.add_argument(
            'course', type=str, help="Course that assignment belongs to.")
        update_assignment.add_argument(
            'homework', type=str, help="Name of assignment to update.")
        update_assignment.add_argument(
            '--autograde-tar', type=str, help="Autograder tar for the assignment.")
        update_assignment.add_argument(
            '--autograde-makefile', type=str, help="Autograder Makefile for the assignment.")
        update_assignment.add_argument(
            '--writeup', type=str, help="PDF writeup for the assignment.")
        update_assignment.add_argument(
            '--handout', type=str, help="Student handout for the assignment.")

        # subparser for upload_chapter
        upload_chapter = subparsers.add_parser(
            "upload_chapter", help="Upload content to a chapter.", formatter_class=Formatter)
        upload_chapter.add_argument(
            "course", help="Course to upload chapter to.")
        upload_chapter.add_argument(
            "book", help="Book that the chapter belongs to.")
        chapter_id_group = upload_chapter.add_mutually_exclusive_group(
            required=True)
        chapter_id_group.add_argument(
            '--chapter_number', default=None, help="Number of chapter to upload to.")
        chapter_id_group.add_argument(
            '--chapter_label', default=None, help="Label of chapter to upload to.")
        file_type_group = upload_chapter.add_mutually_exclusive_group(
            required=True)
        file_type_group.add_argument(
            "--pdf", default=None, help="Upload PDF content.")
        file_type_group.add_argument(
            "--slides", default=None, help="Upload a slideshow in PDF format.")
        file_type_group.add_argument(
            "--xml", default=None, help="Upload an XML/MLX document.")
        upload_chapter.add_argument(
            "--video_url", default=None, help="URL to a video to embed into the chapter.")
        upload_chapter.add_argument(
            "--xml_pdf", default=None, help="PDF version of the XML document for printing.")
        upload_chapter.add_argument("--attach", type=str, nargs='+', default=None,
                                    help="A list of files, folders, or globs to upload as attachments for an XML/MLX document. \
                                          Folders are recursively traversed.")
        return parser, subparsers

    # Verify argument information about both the admin and user CLI's.
    @staticmethod
    def validate_args(args):
        if (args.password is None and args.username is not None) or \
           (args.password is not None and args.username is None):
            exit_with_error("Please supply both username and password")
        if args.credentials is not None and (args.username is not None or args.password is not None):
            exit_with_error(
                "Cannot use a credentials file and input a username/password")


# Class implementing the DiderotUser CLI
class DiderotUser(object):
    def __init__(self, line=None):
        parser, _ = DiderotCLIArgs.generate_user_parser(
            "diderot", "User CLI interface for Diderot.")
        if line is None:
            self.args = parser.parse_args()
        else:
            self.args = parser.parse_args(shlex.split(line))
        DiderotCLIArgs.validate_args(self.args)
        self.setup_client()

    def setup_client(self):
        self.username = self.args.username
        self.password = self.args.password
        if self.username is None:
            creds = DEFAULT_CRED_LOCATIONS
            if self.args.credentials is not None:
                creds = [self.args.credentials] + creds
            for c in creds:
                p = Path(c).expanduser()
                if p.is_file():
                    if (p.stat().st_mode & 0o177) != 0:
                        exit_with_error(
                            "Credentials file must have 0600 permissions. Run `chmod 600 <credentials>` first.")
                    f = p.open('r')
                    data = f.read().strip().split('\n')
                    self.username = data[0]
                    self.password = data[1]
                    f.close()
                    break
                else:
                    if c == self.args.credentials:
                        exit_with_error("Input credentials path is invalid.")
        if self.username is None:
            exit_with_error(
                "Supply your credentials via the CLI or a credentials file!")
        self.api_client = DiderotAPIInterface(self.args.url)
        if not self.api_client.login(self.username, self.password, shouldPrint=False):
            exit_with_error("Login failed.")

    # Utility function for pretty printing of list data.
    def print_list(self, l):
        try:
            cols, _ = os.get_terminal_size(0)
        except:
            cols = 40
        if len(l) == 0:
            maxLen = 20
        else:
            maxLen = max([len(x) for x in l]) + 2
        n = max(((cols // maxLen) - 1), 1)
        final = [l[i * n:(i + 1) * n] for i in range((len(l) + n - 1) // n)]
        for row in final:
            print(" ".join(["{: <" + str(maxLen) + "}"]
                           * len(row)).format(*row))

    def dispatch(self):
        commands = {
            'download_assignment': self.download_assignment,
            'list_assignments': self.list_assignments,
            'list_courses': self.list_courses,
            'submit_assignment': self.submit_assignment,
        }
        func = commands.get(self.args.command, None)
        if func is None:
            exit_with_error("Error parsing.")
        func()
        self.api_client.client.close()

    # For maintainability, keep the dispatch functions in alphabetical order.

    def download_assignment(self):
        if self.api_client.download_assignment(self.args.course, self.args.homework) is None:
            exit_with_error("Failed to download assignment.")
        else:
            print("Successfully downloaded assignment.")

    def list_assignments(self):
        result = self.api_client.list_assignments(self.args.course)
        if result is None:
            exit_with_error("Error retrieving all assignments.")
        else:
            self.print_list([hw['name'] for hw in result])

    def list_courses(self):
        result = self.api_client.list_all_courses()
        if result is None:
            exit_with_error("Error retrieving all courses.")
        else:
            self.print_list([c['label'] for c in result])

    def submit_assignment(self):
        success, res_url = self.api_client.submit_assignment(
            self.args.course, self.args.homework, self.args.handin_path)
        if success:
            print("Assignment submitted successfully. Track your submission's status at the following url: {}".format(res_url))
        else:
            exit_with_error(
                "Something went wrong. Please try submitting on the Diderot website.")


# Class implementing DiderotAdmin CLI
class DiderotAdmin(DiderotUser):
    def __init__(self, line=None, sleep_time=5):
        parser, _ = DiderotCLIArgs.generate_admin_parser(
            "diderot_admin", "Admin CLI interface for Diderot.")
        if line is None:
            self.args = parser.parse_args()
        else:
            self.args = parser.parse_args(shlex.split(line))
        self.sleep_time = sleep_time
        DiderotCLIArgs.validate_args(self.args)
        self.setup_client()

    def dispatch(self):
        commands = {
            'create_chapter': self.create_chapter,
            'create_part': self.create_part,
            'list_books': self.list_books,
            'list_chapters': self.list_chapters,
            'list_parts': self.list_parts,
            'release_chapter': self.release_chapter,
            'unrelease_chapter': self.unrelease_chapter,
            'update_assignment': self.update_assignment,
            'upload_chapter': self.upload_chapter,
        }
        func = commands.get(self.args.command, None)
        if func is None:
            super().dispatch()
        else:
            func()

    # For maintainability, keep the dispatch functions in alphabetical order.

    def create_chapter(self):
        if self.api_client.create_chapter(self.args):
            print("Successfully created chapter.")
        else:
            exit_with_error("Chapter creation failed.")

    def create_part(self):
        if self.api_client.create_part(self.args):
            print("Successfully created part.")
        else:
            exit_with_error("Part creation failed.")

    def list_books(self):
        res = self.api_client.list_books(self.args.course, all=self.args.all)
        if res is None:
            exit_with_error("Error listing books.")
        else:
            self.print_list([c['label'] for c in res])

    def list_chapters(self):
        res = self.api_client.list_chapters(self.args.course, self.args.book)
        if res is None:
            exit_with_error("Error listing chapters.")
        else:
            self.print_list(["{}. {}".format(str(float(c['rank'])).rstrip(
                '0').rstrip('.'), c['title']) for c in res])

    def list_parts(self):
        res = self.api_client.list_parts(self.args.course, self.args.book)
        if res is None:
            exit_with_error("Error listing parts.")
        else:
            self.print_list(["{}. {}".format(c['rank'], c['title'])
                             for c in res])

    def release_chapter(self):
        if self.api_client.release_unrelease_chapter(self.args.course, self.args.book, self.args, release=True):
            print("Success releasing chapter.")
        else:
            exit_with_error("Failure releasing chapter.")

    def unrelease_chapter(self):
        if self.api_client.release_unrelease_chapter(self.args.course, self.args.book, self.args, release=False):
            print("Success unreleasing chapter.")
        else:
            exit_with_error("Failure unreleasing chapter.")

    def update_assignment(self):
        if self.api_client.update_assignment(self.args.course, self.args.homework, self.args):
            print("Success uploading files.")
        else:
            exit_with_error("Uploading files failed. Try using the Web UI.")

    def upload_chapter(self):
        if self.args.video_url is not None and self.args.xml is not None:
            exit_with_error(
                "Cannot use --video_url with xml uploads.\nFailure uploading chapter.")
        if self.args.attach is not None and self.args.xml is None:
            exit_with_error(
                "Cannot use --attach if not uploading xml/mlx.\nFailure uploading chapter.")
        success = self.api_client.upload_chapter(
            self.args.course, self.args.book, self.args, sleep_time=self.sleep_time)
        if not success:
            exit_with_error("Failure uploading chapter.")
        else:
            print("Chapter uploaded successfully.")
