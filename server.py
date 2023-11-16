#!/usr/bin/env python

'''
This is the main Flask server.
'''
from flask import Flask, jsonify
from flask import abort, request
from flask_cors import CORS
from datetime import datetime
import os
import sys
import pickle
import logging
from textwrap3 import wrap
from PostgresHelper import PostgresHelper
from airdna_review_summarizer import AirDNAReviewSummarizer
import speed_distance as sd

# Global variables for this file
app = Flask(__name__,
            static_url_path='',
            static_folder='web/static',
            template_folder='web/templates')
cors = CORS(app, resources={r"/v1/api/*": {"origins": "*"}})
query_cache = {}
query_cache_file_store = 'query_cache.txt'


@app.route('/')
def index():
    return app.send_static_file('index.html'), 200


@app.route('/health')
def health():
    try:
        return jsonify({'message': 'Data server is running fine', 'status': 0}), 200
    except (RuntimeError, Exception) as err:
        return jsonify(
            {"message": 'Data server is down! Error encountered: {0}'.format(err),
             "version": app.config["VERSION"],
             "date": datetime.now(), "status": -1}), 401


@app.route('/reviews/summary')
def show_review_summary():
    return app.send_static_file('show_review_summary.html'), 200

# curl -i -H "Content-Type: application/json" http://localhost:5000/v1/api/reviews/summary/46394374
@app.route('/v1/api/reviews/summary/<string:property_id>', methods=['GET'])
def get_review_summary(property_id):
    """
    Gets the summary along with the raw reviews for a given property
    :param property_id: The property Id
    :return: The results of the query as a dictionary
    """
    review_summarizer = AirDNAReviewSummarizer()
    if not review_summarizer.is_summary_available(property_id):
        print(f"New property encountered. Summarizing reviews for property Id {property_id}. Please wait...")
        review_summarizer.fetch_save_summary_of_reviews_for_single_property(property_id)
        print(f"Summary of reviews are now saved for property id {property_id}")

    postgres = PostgresHelper()
    query_string = f"SELECT" \
                   f"    PROPERTY_ID," \
                   f"    CONSOLIDATED_REVIEW," \
                   f"    SUMMARY, " \
                   f"    CRITICAL_REVIEW " \
                   f"FROM JoshuaConsolidatedRawReviews " \
                   f"WHERE PROPERTY_ID = {property_id}"
    if query_string in query_cache:
        rows = query_cache[query_string]  # Get from cache
    else:
        rows = postgres.query(query_string)
        saveObjectLocally(query_cache_file_store)

    output = {'property_id': rows[0][0], 'ai_generated_summary': rows[0][2]}
    all_lines_of_review = rows[0][3].split('\n')
    final_lines = []
    for line in all_lines_of_review:
        wrapped_lines = wrap(line, 100)
        line_counter = 0
        for wrapped_line in wrapped_lines:
            if line_counter > 0:
                final_lines.append('  ' + wrapped_line)
            else:
                final_lines.append(wrapped_line)
            line_counter += 1

    output['ai_generated_critical_review'] = '\n'.join(final_lines)
    output['reviews'] = rows[0][1].split('|||')

    return jsonify({
        'title': f"Summary and Raw review for property Id {property_id}",
        'query': query_string,
        'data': output
    })


# curl -i -H "Content-Type: application/json" http://localhost:5000/v1/api/property/seek?term=cottage
@app.route('/v1/api/property/seek', methods=['GET'])
def seek_property():
    """
    Gets the summary along with the raw reviews for a given property
    :return: The results of the query as a dictionary
    """
    term = request.args.get('term')
    postgres = PostgresHelper()
    query_string = f"""
    SELECT
    AIRBNB_PROPERTY_ID || ': ' || TITLE AS PROPERTY_NAME
    FROM JoshuaConsolidatedRawReviews JCR
    LEFT JOIN JOSHUAPROPERTIES JP
        ON JCR.PROPERTY_ID = CAST(JP.AIRBNB_PROPERTY_ID AS bigint)
    WHERE (jp.AIRBNB_PROPERTY_ID::VARCHAR ILIKE '%{term}%' OR jp.TITLE ILIKE '%{term}%')
    """
    if query_string in query_cache:
        rows = query_cache[query_string]  # Get from cache
    else:
        rows = postgres.query(query_string)
        saveObjectLocally(query_cache_file_store)

    property_names = []
    for row in rows:
        property_names.append(row[0])

    return jsonify(property_names)


# curl -i -H "Content-Type: application/json" http://localhost:5000/v1/api/property/list/all
@app.route('/v1/api/property/list/all', methods=['GET'])
def list_all_properties_with_lat_lon():
    limit = request.args.get('limit') or 10000
    postgres = PostgresHelper()
    query_string = f"""
    SELECT
        JP.AIRBNB_PROPERTY_ID,
        JP.TITLE,
        COALESCE(JP.BEDROOMS,0)::INT,
        COALESCE(JP.BATHROOMS,0)::INT,
        JP.PROPERTY_TYPE,
        JP.ZIPCODE,
        JP.CITY_NAME,
        JP.CITY_ID,
        JP.STATE_NAME,
        JP.LATITUDE::FLOAT,
        JP.LONGITUDE::FLOAT
    FROM JoshuaConsolidatedRawReviews JCR
    LEFT JOIN JOSHUAPROPERTIES JP
        ON JCR.PROPERTY_ID = CAST(JP.AIRBNB_PROPERTY_ID AS bigint)
    LIMIT {limit}
    """
    if query_string in query_cache:
        rows = query_cache[query_string]  # Get from cache
    else:
        rows = postgres.query(query_string)
        saveObjectLocally(query_cache_file_store)

    global_min_lat = sys.float_info.max
    global_min_lon = sys.float_info.max
    global_max_lat = -sys.float_info.max
    global_max_lon = -sys.float_info.max

    output_rows = []
    for row in rows:
        latitude = float(row[9])
        longitude = float(row[10])

        if latitude > global_max_lat:
            global_max_lat = latitude
        if latitude < global_min_lat:
            global_min_lat = latitude
        if longitude > global_max_lon:
            global_max_lon = longitude
        if longitude < global_min_lon:
            global_min_lon = longitude

        output_rows.append({
            'property_id': row[0],
            'title': row[1],
            'bedrooms': row[2],
            'bathrooms': row[3],
            'property_type': row[4],
            'zipcode': row[5],
            'city': row[6],
            'city_id': row[7],
            'state': row[8],
            'latitude': float(row[9]),
            'longitude': float(row[10])
        })

    global_mid_lon = (global_max_lon + global_min_lon) / 2.0
    global_mid_lat = (global_max_lat + global_min_lat) / 2.0

    if global_min_lat == global_max_lat and global_min_lon == global_max_lon:
        zoom_factor = 10
    else:
        zoom_factor = int(1200000/sd.distance_great_circle(global_min_lat, global_min_lon, global_max_lat, global_max_lon))

    return jsonify({
        'title': f"List of all properties",
        'query': query_string,
        'data': output_rows,
        'info': {
            'center': {
                'lat': global_mid_lat,
                'lon': global_mid_lon
            },
            'bottom_left': {
                'lat': global_min_lat,
                'lon': global_min_lon
            },
            'top_right': {
                'lat': global_max_lat,
                'lon': global_max_lon
            },
            'zoom': min(max(6, zoom_factor), 12)
        }
    })

def saveObjectLocally(dumpfile):
    """
    Saves the in-memory data to a file.
    """
    if len(query_cache) > 0:
        with open(dumpfile, 'wb') as query_cache_file:
            pickle.dump(query_cache, query_cache_file)


def loadFromTextFile(dumpfile):
    """
    Loads previously saved data from file to memory.
    """
    if os.path.exists(dumpfile):
        with open(dumpfile, 'rb') as sensor_readings_file:
            return pickle.load(sensor_readings_file)
    else:
        return {}


if __name__ == '__main__':
    query_cache = loadFromTextFile(query_cache_file_store)
    logging.getLogger().setLevel(logging.INFO)
    postgres_logger = logging.getLogger("postgres.connector")
    postgres_logger.setLevel(logging.INFO)
    app.run(debug=True,
            host="0.0.0.0",
            port=5000,
            use_reloader=True)
