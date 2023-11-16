import psycopg2


class PostgresHelper(object):
    def __init__(self):
        '''
        Reads the environment variables and initializes few parameters.
        '''

        POSTGRES_HOST = 'localhost'
        POSTGRES_USERNAME = 'arka_bagchi'
        POSTGRES_PASSWORD = 'tehkitteh24@'
        POSTGRES_PORT = 5432
        POSTGRES_DB = 'airbnb_reviews'

        self.conn_string = "host=" + str(POSTGRES_HOST) + " port=" + str(POSTGRES_PORT) + " dbname=" + str(POSTGRES_DB) + " user=" + str(POSTGRES_USERNAME) + " password=" + str(POSTGRES_PASSWORD)
        print('PostGRES database to be used: ' + POSTGRES_HOST + ":" + str(POSTGRES_PORT))

        # Check connection to the PostGRES database
        try:
            connection = psycopg2.connect(self.conn_string)
            connection.close()
            print('Successfully connected to PostGRES database.')
        except (RuntimeError, Exception) as err:
            print('Failed to connect to PostGRES database. Please check your environment variables and try again.')
            print('\nTHE APPLICATION WILL NOT WORK PROPERLY.\n')

    def query(self, query_string):
        """
        Executes the query and returns the results
        """
        conn = psycopg2.connect(self.conn_string)
        cursor = conn.cursor()
        cursor.execute(query_string)
        results = cursor.fetchall()
        cursor.close()
        return results

    def execute(self, query_string):
        """
        Executes the query
        """
        conn = psycopg2.connect(self.conn_string)
        conn.autocommit = True
        cursor = conn.cursor()
        cursor.execute(query_string)
        cursor.close()
        return

    @staticmethod
    def close_cursor(self, cursor):
        """
        Closes the connection to the database.
        """
        cursor.close()
