from abc import ABC, abstractmethod
from mysql import connector
from uuid import uuid4
import requests
import re
from config import cookies, headers
import urllib
import os


def get_uuid():
    return str(uuid4())


img_url_pattern = re.compile(
    r'(?P<url>https:\/\/.*\/(?P<filename>.*?(?:\bimg|png|jpeg|jpg\b)))')
connection_params = {
    'host': "localhost",
    'port': 3306,
    'user': "root",
    'password': "root",
    'database': "exam",
}


def create_subject(name: str):
    conn = connector.connect(**connection_params)
    cursor = conn.cursor()

    subject_insert_query = f"INSERT INTO subjects (uuid, name) VALUES (%s, %s)"
    cursor.execute(
        subject_insert_query, (
            str(uuid4()),
            name,
        )
    )
    subject_id = cursor.lastrowid
    conn.commit()
    cursor.close()
    conn.close()

    return subject_id


def get_correct_answer_index(letters):
    return [ord(letter) - ord('a') for letter in letters]


def download_image_explanation(explanation: str, img_folder: str):
    matched = img_url_pattern.findall(explanation)

    for (img_url, img_filename) in matched:
        img_path = os.path.join(img_folder, img_filename)
        print(f'start download {img_url=} to {img_path=}')
        urllib.request.urlretrieve(
            img_url,
            img_path
        )

        # replace img url by local path
        explanation = explanation.replace(img_url, img_path)

    # remove local path to local server path
    explanation = explanation.replace('/Users/lai/Desktop/thi-trac-nghiem/public', 'http://127.0.0.1:8000')
    return explanation


class ApiFactory(ABC):
    def __init__(self, thumbnail: str, exam_name: str, quizz_ids: list, exam_time: int = 180, subject_id: int = 1) -> None:
        self.thumbnail = thumbnail
        self.exam_name = exam_name
        self.quizz_ids = quizz_ids
        self.exam_time = exam_time * 60  # convert min to second
        self.subject_id = subject_id
        self.img_folder = os.path.join(
            os.getcwd(), 'public', 'images', 'subjects', str(subject_id)
        )
        os.makedirs(self.img_folder)

        self.conn = connector.connect(**connection_params)
        self.cursor = self.conn.cursor()
        self.request_url = 'https://funix.udemy.com/api-2.0/quizzes/{}/assessments/?version=5&page_size=250&fields[assessment]=id,assessment_type,prompt,correct_response,section,question_plain,related_lectures&use_remote_version=true'

    def get_data(self, quizz_id: int):
        return requests.get(
            self.request_url.format(quizz_id),
            cookies=cookies,
            headers=headers,
        ).json()

    def run(self):
        exam_number = 1
        for quizz_id in self.quizz_ids:
            exam_id = self.write_exam_to_db(f'{self.exam_name} {exam_number}')
            exam_number += 1

            data = self.get_data(quizz_id)
            for item in data['results']:
                question_id = self.write_question_to_db(
                    item['prompt']['question'],
                    item['prompt']['explanation'],
                    'no note',
                    exam_id,
                    1 if len(item['correct_response']) > 1 else 0,
                )

                correct_answers = get_correct_answer_index(
                    item['correct_response'])

                # write option to db
                answer_index = 0
                for option in item['prompt']['answers']:
                    self.write_option_to_db(
                        option,
                        1 if answer_index in correct_answers else 0,
                        question_id,
                    )
                    answer_index += 1

        # close connection
        self.conn.commit()
        self.cursor.close()
        self.conn.close()

    def write_exam_to_db(self, exam_name):
        exam_insert_query = f"INSERT INTO exams (uuid, name, thumbnail, time, subject_id) VALUES (%s, %s, %s, %s, %s)"
        self.cursor.execute(
            exam_insert_query, (
                get_uuid(),
                exam_name,
                self.thumbnail,
                self.exam_time,
                self.subject_id,
            )
        )
        return self.cursor.lastrowid

    def write_question_to_db(self, question_text: str, explaination: str, note: str, exam_id: int, is_multichoice: int):
        explaination = download_image_explanation(
            explaination, self.img_folder)

        # insert to question
        question_insert_query = "INSERT INTO questions (uuid, text, explaination, note, is_multichoice) VALUES (%s, %s, %s, %s, %s)"
        self.cursor.execute(question_insert_query,
                            (get_uuid(), question_text, explaination, note, is_multichoice))

        question_id = self.cursor.lastrowid
        # insert to exam question
        exam_question_insert_query = "INSERT INTO exam_questions (exam_id, question_id) VALUES (%s, %s)"
        self.cursor.execute(exam_question_insert_query,
                            (exam_id, question_id))

        return question_id

    def write_option_to_db(self, option_html: str, is_correct: bool, question_id: int):
        option_insert_query = "INSERT INTO options (text, is_correct, question_id) VALUES (%s, %s, %s)"
        self.cursor.execute(option_insert_query, (
            str(option_html), is_correct, question_id))

    # def update_question_multichoice(self, question_id: int):
    #     update_question_query = f"update questions set is_multichoice=1 where id={question_id}"
    #     self.cursor.execute(update_question_query)
