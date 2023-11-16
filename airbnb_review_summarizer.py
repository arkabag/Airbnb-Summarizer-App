"""
Creates a JSONL file from the data in the database for the consolidated reviews.
A JSONL must contain three fields as follows:
{
    "messages": [
        {"role": "system", "content": "Given the concatenated reviews for a property, provide a detailed, objective, and sentiment-aware summary capturing the unique features of the property, the general sentiment of the reviewers, specifics about the host/manager, notable amenities, and any standout experiences or facilities mentioned."},
        {"role": "user", "content": "This place was an amazing site for camping outside of the Joshua tree park.|||Exactly how it is described. No neighbors, Super private campground with great views. },
        {"role": "assistant", "content": "This remote and beautiful spot for camping is located just minutes outside of a small town. The property offers much-needed privacy and features a concrete structure providing great utility for storage, protection from the sun and wind, and more. Reviewers appreciate the privacy, open space, views, and amenities, with one camper even spotting a kangaroo mouse! The property is described as \"barebones\" but with the addition of shade from camping things and possibility of a fire pit, it's even more enjoyable. Nikki was a great host, making it easy to find the property and providing helpful tips, and reviewers enjoyed making memories here. However, visitors should be aware that vehicles survival in this terrain is not guaranteed and to make sure to burn any cardboard they don't plan on bringing back with them."}
    ]
}
Note that there are three fields in this JSON. The system role is the prompt which must be exactly the same for all items.
The user role is the consolidated review that must not exceed 4096 tokens. You need to crop the review if it exceeds that.
The database column contains the most recent reviews first, so if you crop it, it will have the latest reviews that fit.
The assistant role is the training summary, which we are not generating here. Instead of doing it manually, we can use the OpenAI API to populate it.
"""
import json

summary_prompt = """As an expert travel agent, please provide a concise summary with no more than 250 words, of \
customer reviews which are separated by '|||', for this AirBNB property \
including key features, associated facilities, and a brief description of the hosts, ending with \
a one-line description of the overall impression at the end."""

critical_review_prompt = """"You are an AI assistant with expertise in real estate and Airbnb investments. \
Analyze and summarize the concatenated reviews for a specific Airbnb property, focusing on key aspects for an investor. \
Present findings in a structured, bullet-point format, within 300 words, with specificity and balance. \
Include:

Property Highlights:
 - Describe standout positive features with details.
Areas for Improvement:
 - Specify recurring negative aspects with frequency or impact.
Location Analysis:
 - Emphasize location advantages with specifics.
Investment Insights:
 - Suggest specific improvements or upgrades for enhanced value and guest satisfaction.
Overall Guest Satisfaction:
 - Analyze the overall sentiment and satisfaction level from the reviews.
Note: Maintain a balanced view, highlighting unique features and actionable insights for an investor."""

import tiktoken
import datetime as dt
from PostgresHelper import PostgresHelper
import string
from openai import OpenAI

client = OpenAI(api_key='INSERT API KEY HERE')
import os
import time

cost_per_100k_tokens = 0.80


class AirDNAReviewSummarizer(object):
    def __init__(self):
        self.postgres_helper = PostgresHelper()

    def num_tokens_from_string(self, string: str, encoding_name: str) -> int:
        """Returns the number of tokens in a text string."""
        encoding = tiktoken.get_encoding(encoding_name)
        num_tokens = len(encoding.encode(string))
        return num_tokens

    def crop_string_to_max_tokens(self, string: str, encoding_name: str, max_tokens:int) -> string:
        """Crops the string to meet the max number of tokens."""
        num_prompt_tokens = self.num_tokens_from_string(summary_prompt, "cl100k_base")
        encoding = tiktoken.get_encoding(encoding_name)
        encoded_cropped_list = encoding.encode(string)[:(max_tokens-num_prompt_tokens)]
        return encoding.decode(encoded_cropped_list)

    def get_consolidated_reviews_for_single_property(self, property_id):
        sql = f"""
        SELECT
            CONSOLIDATED_REVIEW
        FROM JoshuaConsolidatedRawReviews
        WHERE PROPERTY_ID = {property_id}
        """
        print(sql)
        query_results = self.postgres_helper.query(sql)
        if len(query_results) > 0:
            return query_results[0][0]
        else:
            return ''

    def get_property_reviews(self, limit=10):
        sql = f"""
        SELECT
            PROPERTY_ID, CONSOLIDATED_REVIEW
            FROM JoshuaConsolidatedRawReviews
            WHERE lengthCONSOLIDATED_REVIEW) > 0
            AND SUMMARY IS NULL
            LIMIT {limit}
        """
        query_results = self.postgres_helper.query(sql)
        return query_results

    def get_reviews_for_summarized_properties(self, limit=10):
        sql = f"""
        SELECT
            PROPERTY_ID, CONSOLIDATED_REVIEW
            FROM JoshuaConsolidatedRawReviews
            WHERE length(CONSOLIDATED_REVIEW) > 0
            AND CRITICAL_REVIEW IS NULL
            AND (length(summary) > 0 OR SUMMARY IS NOT NULL)
            LIMIT {limit}
        """
        query_results = self.postgres_helper.query(sql)
        return query_results

    def is_summary_available(self, propertyId):
        postgres = PostgresHelper()
        query_string = f"""
        SELECT
            property_id,
            summary
        FROM JoshuaConsolidatedRawReviews
        WHERE (length(summary) > 0 OR SUMMARY IS NOT NULL)
        AND property_id = {propertyId}
        """
        rows = postgres.query(query_string)
        return_value = False
        if len(rows) > 0:
            return_value = True

        return return_value

    def format_review(self, review, max_tokens=4096):
        """
        Formats a review to ensure that the tokens are less than 4096
        :param review:
        :return:
        """
        while (True):
            token_count = self.num_tokens_from_string(review, "cl100k_base")
            if token_count > max_tokens:
                review = self.crop_string_to_max_tokens(review, "cl100k_base", 4096)
                #full_text = tokenizer.decode(tokenizer.encode(full_text)[:text_max_length])
                #desired_fraction = max_tokens / token_count
                #desired_length = int(len(review) * desired_fraction)
                #review = review[:desired_length]
                continue
            else:
                break

        return review, token_count

    def save_property_review_summary(self, property_id, summary):
        sql = f"""
        UPDATE JoshuaConsolidatedRawReviews
        SET SUMMARY = '{summary}'
        WHERE PROPERTY_ID = {property_id}
        """
        self.postgres_helper.execute(sql)

    def save_critical_review(self, property_id, critical_review):
        sql = f"""
        UPDATE JoshuaConsolidatedRawReviews
        SET CRITICAL_REVIEW = '{critical_review}'
        WHERE PROPERTY_ID = {property_id}
        """
        self.postgres_helper.execute(sql)

    def generate_clean_csv(self, limit=10):
        # Open a CSV file for writing (tab-separated)
        basename = "/tmp/token_worthy_reviews"
        suffix = dt.datetime.now().strftime("%y%m%d_%H%M%S")
        temp_filename = "_".join([basename, suffix, '.csv'])  # e.g. '/tmp/token_worthy_reviews_120508_171442_.csv'

        file = open(temp_filename, "w")
        file.write(f"property_id\tconsolidated_review\ttoken_count\n")

        property_reviews = self.get_property_reviews(2 * limit)
        total_tokens = 0
        property_counter = 0

        for property_review in property_reviews:
            property_id = property_review[0]
            raw_consolidated_review = property_review[1].replace('\n', ' ').replace('\t', ' ').replace('["','').replace('"]','').replace('\\"', '"')
            token_worthy_review, token_count = self.format_review(raw_consolidated_review)

            if token_count > 0:
                filtered_consolidated_review = ''.join(filter(lambda x: x in string.printable, token_worthy_review))
                total_tokens += token_count
                property_counter += 1
                file.write(f"{property_id}\t{filtered_consolidated_review}\t{token_count}\n")
            if property_counter >= limit:
                break

        file.close()
        total_cost = total_tokens * cost_per_100k_tokens / 100000
        print(f"Total properties: {property_counter}")
        print(f"Total tokens: {total_tokens}")
        print(f"Estimated cost of generating model: ${total_cost}")

    def generate_openai_jsonl(self, limit=10):
        # Open a CSV file for writing (tab-separated)
        basename = "/tmp/token_worthy_reviews"
        suffix = dt.datetime.now().strftime("%y%m%d_%H%M%S")
        temp_filename = "_".join([basename, suffix]) + '.jsonl'  # e.g. '/tmp/token_worthy_reviews_120508_171442.jsonl'

        file = open(temp_filename, "w")

        property_reviews = self.get_property_reviews(2 * limit)
        total_tokens = 0
        property_counter = 0

        for property_review in property_reviews:
            property_id = property_review[0]
            raw_consolidated_review = property_review[1].replace('\n', ' ').replace('\t', ' ').replace('["','').replace('"]','').replace('\\"', '"')
            token_worthy_review, token_count = self.format_review(raw_consolidated_review)

            if token_count > 0:
                filtered_consolidated_review = ''.join(filter(lambda x: x in string.printable, token_worthy_review))

                # {"messages": [{"role": "system", "content": "You are an overly friendly hospitality chatbot named Chatner who just loves to help people, and you're not satisfied unless the customer is completely satisfied."}, {"role": "user", "content": "Is breakfast included?"}, {"role": "assistant", "content": "Oh, I'm thrilled you asked about breakfast! Yes, it's included and served from 7 to 10 a.m. in the main dining area. Enjoy!"}]}
                system_role = {
                    "role": "system",
                    "content": summary_prompt
                }
                user_role = {
                    "role": "user",
                    "content": filtered_consolidated_review
                }
                total_tokens += token_count
                property_counter += 1
                complete_message = {
                    "messages": [
                        system_role,
                        user_role
                    ]
                }
                file.write(f"{json.dumps(complete_message)}\n")
                if property_counter >= limit:
                    break

        file.close()
        total_cost = total_tokens * cost_per_100k_tokens / 100000
        print(f"Total properties: {property_counter}")
        print(f"Total tokens: {total_tokens}")
        print(f"Estimated cost of generating model: ${total_cost}")

    def create_summary_from_base_model(self, chunk):
        response = client.chat.completions.create(model="gpt-4-1106-preview",
        messages=[
            {"role": "system", "content": f"{summary_prompt}"},
            {"role": "user", "content": f"{chunk}"}
        ],
        temperature=1,
        max_tokens=1024,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0)
        print(response)
        return response

    def create_critical_review_from_base_model(self, chunk):
        response = client.chat.completions.create(model="gpt-4-1106-preview",
        messages=[
            {"role": "system", "content": f"{critical_review_prompt}"},
            {"role": "user", "content": f"{chunk}"}
        ],
        temperature=0.5,
        max_tokens=1024,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0)
        print(response)
        return response

    def fetch_save_summary_of_reviews_for_single_property(self, property_id):
        property_review = self.get_consolidated_reviews_for_single_property(property_id)

        # Clean up the consolidated review
        raw_consolidated_review = property_review.replace('\n', ' ').replace('\t', ' ').replace('["', '').replace('"]', '').replace('\\"', '"')
        token_worthy_review, token_count = self.format_review(raw_consolidated_review)

        if token_count > 0:
            print(f"Summarizing reviews for property Id {property_id} with {token_count} tokens...")
            filtered_consolidated_review = ''.join(filter(lambda x: x in string.printable, token_worthy_review))

            # Get the summary first
            response = self.create_summary_from_base_model(filtered_consolidated_review)
            the_summary = response.choices[0].message.content
            the_summary_for_sql = the_summary.replace("'", "''")  # Save the summary to the database
            self.save_property_review_summary(property_id, the_summary_for_sql)

            response = self.create_critical_review_from_base_model(filtered_consolidated_review)
            the_critical_review = response.choices[0].message.content
            the_critical_review_for_sql = the_critical_review.replace("'", "''")  # Save critical review to the database
            self.save_critical_review(property_id, the_critical_review_for_sql)
        else:
            print(f"Skipped property Id {property_id}. No tokens found.")
            self.save_property_review_summary(property_id, "")

    def generate_property_summary_from_basemodel(self, limit=10):
        # Open a CSV file for writing (tab-separated)
        basename = "/tmp/summary_of_reviews"
        suffix = dt.datetime.now().strftime("%y%m%d_%H%M%S")
        temp_filename = "_".join([basename, suffix]) + '.csv'  # e.g. '/tmp/summary_of_reviews_120508_171442.csv'

        file = open(temp_filename, "w")
        file.write(f"property_id\tsummary\tprompt_tokens\tcompletion_tokens\ttotal_tokens\tfinish_reason\n")

        property_reviews = self.get_property_reviews(2 * limit)
        grand_token_count = 0
        property_counter = 0

        for property_review in property_reviews:
            property_id = property_review[0]

            raw_consolidated_review = property_review[1].replace('\n', ' ').replace('\t', ' ').replace('["','').replace('"]','').replace('\\"', '"')
            token_worthy_review, token_count = self.format_review(raw_consolidated_review)

            if token_count > 0:
                print(f"Summarizing reviews for property Id {property_id} with {token_count} tokens...")
                filtered_consolidated_review = ''.join(filter(lambda x: x in string.printable, token_worthy_review))
                response = self.create_summary_from_base_model(filtered_consolidated_review)

                the_summary = response.choices[0].message.content
                prompt_tokens = response.usage.prompt_tokens
                completion_tokens = response.usage.completion_tokens
                total_tokens = response.usage.total_tokens
                finish_reason = response.choices[0].finish_reason
                file.write(f"{property_id}\t{the_summary}\t{prompt_tokens}\t{completion_tokens}\t{total_tokens}\t{finish_reason}\n")

                # Save it to the database
                the_summary_for_sql = the_summary.replace("'", "''")
                self.save_property_review_summary(property_id, the_summary_for_sql)

                grand_token_count += total_tokens
                property_counter += 1
                print("Waiting for 10 seconds...")
                time.sleep(10)
            else:
                print(f"Skipped property Id {property_id}. No tokens found.")
                self.save_property_review_summary(property_id, "")

            if property_counter >= limit:
                break

        file.close()
        total_cost = grand_token_count * cost_per_100k_tokens / 100000
        print(f"Summaries are saved in file: {temp_filename}")
        print(f"Total properties: {property_counter}")
        print(f"Total tokens: {grand_token_count}")
        print(f"Cost of generating model: ${total_cost}")


    def generate_property_critical_reviews_from_basemodel(self, limit=10):
        # Open a CSV file for writing (tab-separated)
        basename = "/tmp/summary_of_reviews"
        suffix = dt.datetime.now().strftime("%y%m%d_%H%M%S")
        temp_filename = "_".join([basename, suffix]) + '.csv'  # e.g. '/tmp/summary_of_reviews_120508_171442.csv'

        file = open(temp_filename, "w")
        file.write(f"property_id\tsummary\tprompt_tokens\tcompletion_tokens\ttotal_tokens\tfinish_reason\n")

        property_reviews = self.get_reviews_for_summarized_properties(2 * limit)
        grand_token_count = 0
        property_counter = 0

        for property_review in property_reviews:
            property_id = property_review[0]
            raw_consolidated_review = property_review[1].replace('\n', ' ').replace('\t', ' ').replace('["','').replace('"]','').replace('\\"', '"')
            token_worthy_review, token_count = self.format_review(raw_consolidated_review)

            if token_count > 0:
                print(f"Summarizing reviews for property Id {property_id} with {token_count} tokens...")
                filtered_consolidated_review = ''.join(filter(lambda x: x in string.printable, token_worthy_review))
                response = self.create_critical_review_from_base_model(filtered_consolidated_review)

                the_critical_review = response['choices'][0]['message']['content']
                prompt_tokens = response['usage']['prompt_tokens']
                completion_tokens = response['usage']['completion_tokens']
                total_tokens = response['usage']['total_tokens']
                finish_reason = response['choices'][0]['finish_reason']
                file.write(f"{property_id}\t{the_critical_review}\t{prompt_tokens}\t{completion_tokens}\t{total_tokens}\t{finish_reason}\n")

                # Save it to the database
                the_critical_review_for_sql = the_critical_review.replace("'", "''")
                self.save_critical_review(property_id, the_critical_review_for_sql)

                grand_token_count += total_tokens
                property_counter += 1
                print("Waiting for 10 seconds...")
                time.sleep(10)
            else:
                print(f"Skipped property Id {property_id}. No tokens found.")
                self.save_property_review_summary(property_id, "")

            if property_counter >= limit:
                break

        file.close()
        total_cost = grand_token_count * cost_per_100k_tokens / 100000
        print(f"Summaries are saved in file: {temp_filename}")
        print(f"Total properties: {property_counter}")
        print(f"Total tokens: {grand_token_count}")
        print(f"Cost of generating model: ${total_cost}")


if __name__ == '__main__':
    generator = AirDNAReviewSummarizer()
    #generator.generate_clean_csv(10)
    #generator.generate_openai_jsonl(10)
    generator.generate_property_summary_from_basemodel(10)
    generator.generate_property_critical_reviews_from_basemodel(10)
