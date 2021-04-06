from datetime import date
from datetime import datetime
import json
import math
import os
from os import path
import pandas as pd
import requests
import statistics
import time


class Artist:
    def __init__(self, name=None, spotify_id=None, musicbrainz_id=None):
        self.spotify_id = spotify_id
        self.musicbrainz_id = musicbrainz_id
        self.name = name
        self.spotify_artist_diversity = None
        self.spotify_genre_diversity = None
        self.touring_artist_diversity = None
        self.touring_genre_diversity = None


class RequestManager:
    def __init__(self, request_log='request_log.txt', max_request_per_second=0.5, max_requests_per_day=1400):
        self.request_log = request_log
        self.f1 = []
        self.requests_made_today = 0
        self.over_daily_request_limit = False
        self.max_request_per_second = max_request_per_second
        self.max_requests_per_day = max_requests_per_day

    def new_request(self, request):
        self.check_request_log()
        over_daily_request_limit = self.over_daily_request_limit

        print('Requests made today:')
        print(self.requests_made_today)
        #         print('Over daily request limit:')
        #         print(over_daily_request_limit)

        if not over_daily_request_limit:
            # Run request
            #             print('I am formally making a request')

            response = self.make_request(request)
            #             print(response)

            # Write a line to the log to record that a request was made
            request_log = self.request_log
            f1 = open(request_log, 'a')
            f1.write('\n' + str(response.status_code))
            f1.close()
        else:
            print('You have hit the daily request limit for setlist.fm! Please wait until tomorrow.')
            response = None
        return response

    def check_request_log(self):
        # Check REQUEST_LOG for how many requests have already been made today
        request_log = self.request_log
        log_exists = os.path.exists(request_log)

        t = date.today()
        todays_date = t.strftime('%Y-%m-%d')

        if log_exists:
            f1 = open(request_log, 'r')
            all_lines = f1.readlines()
            f1.close()
            log_date = all_lines[0].strip()
            print(log_date)
            if log_date == todays_date:
                requests_made_today = len(all_lines) - 1
                if requests_made_today >= self.max_requests_per_day:
                    over_daily_request_limit = True
                else:
                    over_daily_request_limit = False
            else:
                # If the log is old, delete it and make a new one
                os.remove(request_log)
                f1 = open(request_log, 'a')
                f1.write(todays_date)
                f1.close()
                requests_made_today = 0
                over_daily_request_limit = False

        else:
            f1 = open(request_log, 'a')
            f1.write(todays_date)
            f1.close()
            requests_made_today = 0
            over_daily_request_limit = False

        self.f1 = f1
        self.requests_made_today = requests_made_today
        self.over_daily_request_limit = over_daily_request_limit

    def make_request(self, request):
        url_stem = "https://api.setlist.fm/rest/1.0/"
        request_type = request['type']
        if request_type == 'artist':
            artist_code = request['artist']
            code = artist_code
        elif request_type == 'venue':
            venue_code = request['venue']
            code = venue_code
        else:
            code = None
        request_url = url_stem + request_type + '/' + code + '/setlists'
        headers = request['headers']
        params = request['params']
        response = requests.get(request_url, headers=headers, params=params)
        print(response.status_code)
        time.sleep(1 / self.max_request_per_second)
        return response


class BandCacheManager:
    def __init__(self, band_cache_file='band_cache.txt'):
        self.band_cache_file = band_cache_file
        self.band_database = {}
        if not path.exists(band_cache_file):
            self.write_band_cache_file()

    def read_band_cache_file(self):
        band_cache_file = self.band_cache_file
        with open(band_cache_file) as json_file:
            band_database = json.load(json_file)
        self.band_database = band_database
        return band_database

    def write_band_cache_file(self):
        band_database = self.band_database
        band_cache_file = self.band_cache_file
        with open(band_cache_file, 'w') as outfile:
            json.dump(band_database, outfile)

    def set_band_cache(self, band_database=None):
        self.band_database = band_database

    def get_band_cache(self):
        return self.band_database


class FindTourMates:
    def __init__(self, primary_band_mbid=None, headers=None):
        self.primary_band_mbid = primary_band_mbid
        self.headers = headers
        self.band_cache_manager = None
        self.band_database = None

    def run(self):
        primary_band_mbid = self.primary_band_mbid
        headers = self.headers
        # 1. Load cached data
        band_database, checklist, old_df, artist_name, done_for_the_day = self.check_band_cache(primary_band_mbid,
                                                                                                headers)

        # 2. Download tour data
        combined_df = self.download_tour_data(primary_band_mbid, checklist, old_df, headers, done_for_the_day)

        # 3. Save data and write to cache file
        self.save_data(primary_band_mbid, checklist, combined_df, band_database, artist_name)

    def set_band_cache_file(self, band_cache_file='band_cache.txt'):
        band_cache_manager = BandCacheManager(band_cache_file)
        self.band_cache_manager = band_cache_manager

    def check_band_cache(self, primary_band_mbid, headers):
        done_for_the_day = False
        band_cache_manager = self.band_cache_manager
        band_database = band_cache_manager.read_band_cache_file()
        checklist = []

        # Query for band
        if primary_band_mbid in band_database:
            checklist = band_database[primary_band_mbid]['checklist']
            tour_mates_json = band_database[primary_band_mbid]['similarBands']
            old_df = pd.read_json(tour_mates_json)
            artist_name = band_database[primary_band_mbid]['name']
        else:
            # Initialize empty similar bands JSON dataframe
            empty_df = pd.DataFrame()
            empty_df['mbid'] = []
            empty_df['name'] = []
            empty_df['count'] = []
            empty_json = empty_df.to_json()
            old_df = pd.read_json(empty_json)
            artist_name = None
        if not checklist:
            checklist, artist_name, done_for_the_day = self.make_checklist(primary_band_mbid, headers)
        return band_database, checklist, old_df, artist_name, done_for_the_day

    @staticmethod
    def make_checklist(primary_band_mbid, headers):
        done_for_the_day = False
        params = {'p': 1}
        r = {'type': 'artist', 'artist': primary_band_mbid, 'headers': headers, 'params': params}
        rm1 = RequestManager()
        response = rm1.new_request(r)
        primary_band_checklist = []
        primary_band_name = []
        if not response:
            done_for_the_day = True
        else:
            shows_raw = json.loads(response.text)
            primary_band_name = shows_raw['setlist'][0]['artist']['name']
            max_pages = math.ceil(shows_raw['total'] / shows_raw['itemsPerPage'])

            primary_band_shows_dict = {}
            for p in range(1, max_pages):
                params = {'p': p}
                r = {'type': 'artist', 'artist': primary_band_mbid, 'headers': headers, 'params': params}
                rm1 = RequestManager()
                response = rm1.new_request(r)
                if not response:
                    done_for_the_day = True
                shows_raw = json.loads(response.text)
                for i in range(0, len(shows_raw['setlist'])):
                    show_id = shows_raw['setlist'][i]['id']
                    primary_band_shows_dict[show_id] = shows_raw['setlist'][i]

            for show in primary_band_shows_dict:
                checklist_entry = {'venue': primary_band_shows_dict[show]['venue']['id'],
                                   'date': primary_band_shows_dict[show]['eventDate'],
                                   'complete': False}
                primary_band_checklist.append(checklist_entry)
        if done_for_the_day:
            primary_band_checklist = []
            primary_band_name = []
        return primary_band_checklist, primary_band_name, done_for_the_day

    def download_tour_data(self, primary_band_mbid, checklist, old_df, headers, done_for_the_day):
        all_bands = []
        # 1. Download data
        for show in range(0, len(checklist)):
            print(checklist[show])
            if not done_for_the_day:
                if not checklist[show]['complete']:
                    venue_code = checklist[show]['venue']
                    show_date = datetime.strptime(checklist[show]['date'], '%d-%m-%Y')
                    output_page, direction, done_for_the_day = find_show(venue_code, show_date, headers)
                    touring_bands, done_for_the_day = extract_touring_bands(venue_code, show_date, headers, output_page,
                                                                            primary_band_mbid, direction)
                    all_bands.append(touring_bands)
                    if not done_for_the_day:
                        checklist[show]['complete'] = True

        # 2. Turn raw band data into unique bands and counts
        touring_bands_count = {}
        for i in range(0, len(all_bands)):
            for band_code in all_bands[i]:
                touring_bands_count[band_code] = touring_bands_count.get(band_code, {})
                touring_bands_count[band_code]['count'] = touring_bands_count[band_code].get('count', 0) + 1
                touring_bands_count[band_code]['name'] = touring_bands_count[band_code].get('name',
                                                                                            all_bands[i][band_code])

        # 3. Convert to dataframe format
        df = pd.DataFrame()
        df['mbid'] = []
        df['name'] = []
        df['count'] = []
        for band in touring_bands_count:  # turn into pandas dataframe
            mbid = band
            name = touring_bands_count[band]['name']
            count = touring_bands_count[band]['count']
            df_row = pd.DataFrame([[mbid, name, count]], columns=['mbid', 'name', 'count'])
            df = df.append(df_row)

        # 4. Combine all of the previously downloaded and compiled data with the dataset we just got
        combined_df = self.combine_dataframes(old_df, df)
        return combined_df

    @staticmethod
    def combine_dataframes(old_df, new_df):
        combined_df = old_df.reset_index(drop=True)
        for index, row in new_df.iterrows():
            current_mbid = row['mbid']
            current_count = row['count']
            if any(combined_df['mbid'] == current_mbid):
                i = combined_df.index[combined_df['mbid'] == current_mbid]
                combined_df.iat[i[0], 2] = combined_df['count'][i] + current_count
            else:
                combined_df = combined_df.append(row)
            combined_df.reset_index(inplace=True, drop=True)
        combined_df.reset_index(inplace=True, drop=True)
        return combined_df

    def save_data(self, primary_band_mbid, checklist, combined_df, band_database, artist_name):
        json_df = combined_df.to_json()
        primary_band = artist_name
        band_cache_entry = {'name': primary_band, 'checklist': checklist, 'similarBands': json_df}
        band_database[primary_band_mbid] = band_cache_entry
        self.band_database = band_database
        band_cache_manager = self.band_cache_manager
        band_cache_manager.set_band_cache(band_database)
        band_cache_manager.write_band_cache_file()

    def spotify_uris_from_database(self, primary_band_mbid, artist_id_cross_reference):
        band_database = self.band_database
        if band_database:
            tour_mates_df = pd.read_json(band_database[primary_band_mbid]['similarBands'])
            tour_mates_df.sort_values('count', inplace=True, ascending=False)
            tour_mates_df.reset_index(inplace=True, drop=True)
            spotify_uris = []
            if len(tour_mates_df) > 10:
                for j in range(0, 10):
                    spotify_uris.append(artist_id_cross_reference[tour_mates_df['name'][j]].spotify_id)
            return spotify_uris


def find_show(venue_code, show_date, headers):
    # Within a given venue's data, a single show will span multiple entries, one for each band that plays. And shows
    # can be very large (for example if they're festivals), which means they can span across multiple database pages.
    # Fortunately, since the entries are ordered by data, we can either find the first or last entry for a show and
    # proceed entry by entry until we're done. That's the goal of this function. The output page and direction are
    # sent directly to the next function: "extract_touring_bands".
    done_for_the_day = False
    start_found = False
    end_found = False
    current_page = 1
    params = {
        'p': current_page
    }

    r2 = {'type': 'venue', 'venue': venue_code, 'headers': headers, 'params': params}
    rm2 = RequestManager()
    response2 = rm2.new_request(r2)
    output_page = 1
    direction = 'forward'
    if not response2:
        done_for_the_day = True
    else:
        venue_shows_raw = json.loads(response2.text)
        venue_page_min = 1
        venue_page_max = math.ceil(venue_shows_raw['total'] / venue_shows_raw['itemsPerPage'])
        page_search_space = [venue_page_min, venue_page_max]

        newest_show_on_page_date = datetime.strptime(venue_shows_raw['setlist'][0]['eventDate'], '%d-%m-%Y')
        oldest_show_on_page_date = datetime.strptime(venue_shows_raw['setlist'][-1]['eventDate'], '%d-%m-%Y')

        new_page = None
        if newest_show_on_page_date >= show_date >= oldest_show_on_page_date:  # Is the show anywhere on this page?
            if newest_show_on_page_date == show_date == oldest_show_on_page_date:  # The show spans the entire page
                if current_page == venue_page_max:
                    end_found = True
                    output_page = current_page
                    direction = 'backward'
                if current_page == venue_page_min:
                    start_found = True
                    output_page = current_page
                    direction = 'forward'
                else:
                    new_page = current_page - 1
                    print(new_page)
            if oldest_show_on_page_date < show_date:  # Last entry is on page
                end_found = True
                output_page = current_page
                direction = 'backward'
            if newest_show_on_page_date > show_date:  # First entry is on page
                start_found = True
                output_page = current_page
                direction = 'forward'

        if newest_show_on_page_date < show_date:  # Is the show on a previous page?
            page_search_space[1] = current_page - 1
            new_page = math.floor(statistics.mean(page_search_space))
            print(page_search_space)
            print(new_page)

        if oldest_show_on_page_date > show_date:  # Is the show on a later page?
            page_search_space[0] = current_page + 1
            new_page = math.floor(statistics.mean(page_search_space))
            print(page_search_space)
            print(new_page)

        been_here = False
        while not start_found and not end_found:
            current_page = new_page
            print('In while loop')
            print('Current page is:')
            print(current_page)
            params = {
                'p': current_page
            }
            r2 = {'type': 'venue', 'venue': venue_code, 'headers': headers, 'params': params}
            rm2 = RequestManager()
            response2 = rm2.new_request(r2)
            if not response2:
                done_for_the_day = True
                start_found = True
                output_page = 1
                direction = 'forward'
            else:
                venue_shows_raw = json.loads(response2.text)
                newest_show_on_page_date = datetime.strptime(venue_shows_raw['setlist'][0]['eventDate'], '%d-%m-%Y')
                oldest_show_on_page_date = datetime.strptime(venue_shows_raw['setlist'][-1]['eventDate'], '%d-%m-%Y')

                if newest_show_on_page_date >= show_date >= oldest_show_on_page_date:  # Is the show on this page?
                    print('The show is on this page')
                    if newest_show_on_page_date == show_date == oldest_show_on_page_date:  # The show spans the page
                        print('The show spans the entire page')
                        if current_page == venue_page_max:
                            end_found = True
                            output_page = current_page
                            direction = 'backward'
                        if current_page == venue_page_min:
                            start_found = True
                            output_page = current_page
                            direction = 'forward'
                        else:
                            if been_here:
                                start_found = True
                                output_page = current_page
                                direction = 'forward'
                            else:
                                new_page = current_page - 1
                                been_here = True
                                print(new_page)
                    if oldest_show_on_page_date < show_date:  # Last entry is on page
                        end_found = True
                        output_page = current_page
                        direction = 'backward'
                    if newest_show_on_page_date > show_date:  # First entry is on page
                        start_found = True
                        output_page = current_page
                        direction = 'forward'

                if newest_show_on_page_date < show_date:  # Is the show on a later page?
                    page_search_space[1] = current_page - 1
                    new_page = math.floor(statistics.mean(page_search_space))
                    print(page_search_space)
                    print(new_page)

                if oldest_show_on_page_date > show_date:  # Is the show on a later page?
                    page_search_space[0] = current_page + 1
                    new_page = math.floor(statistics.mean(page_search_space))
                    print(page_search_space)
                    print(new_page)

    return output_page, direction, done_for_the_day


def extract_touring_bands(venue_code, show_date, headers, page_no, primary_artist_code, direction='forward'):
    done_for_the_day = False
    touring_bands = {}
    shows_on_page = True
    current_page = page_no

    while shows_on_page:
        params = {
            'p': current_page
        }

        r2 = {'type': 'venue', 'venue': venue_code, 'headers': headers, 'params': params}
        rm2 = RequestManager()
        print('Current page:')
        print(current_page)
        response2 = rm2.new_request(r2)
        if not response2:
            done_for_the_day = True
            shows_on_page = False
        else:
            venue_shows_raw = json.loads(response2.text)
            venue_page_min = 1
            venue_page_max = math.ceil(venue_shows_raw['total'] / venue_shows_raw['itemsPerPage'])

            newest_show_on_page_date = datetime.strptime(venue_shows_raw['setlist'][0]['eventDate'], '%d-%m-%Y')
            oldest_show_on_page_date = datetime.strptime(venue_shows_raw['setlist'][-1]['eventDate'], '%d-%m-%Y')

            if newest_show_on_page_date >= show_date >= oldest_show_on_page_date:  # Is the show anywhere on this page?

                for i in range(0, len(venue_shows_raw['setlist'])):
                    current_show_date = datetime.strptime(venue_shows_raw['setlist'][i]['eventDate'], '%d-%m-%Y')
                    if current_show_date == show_date:
                        current_band_code = venue_shows_raw['setlist'][i]['artist']['mbid']
                        if not current_band_code == primary_artist_code:
                            touring_bands[current_band_code] = venue_shows_raw['setlist'][i]['artist']['name']
                if direction == 'forward':
                    if current_page == venue_page_max:
                        shows_on_page = False  # We're done
                    else:
                        current_page = current_page + 1
                if direction == 'backward':
                    if current_page == venue_page_min:
                        shows_on_page = False  # We're done
                    else:
                        current_page = current_page - 1
            else:
                shows_on_page = False

    return touring_bands, done_for_the_day


def load_artists():
    all_artists_list = []

    the_acacia_strain = Artist('The Acacia Strain', '4tDkeVxH0CSkNiLVrsYmQs', '08bebce9-33fa-4ae9-9992-4e5d137d655b')
    all_artists_list.append(the_acacia_strain)

    afi = Artist('AFI', '19I4tYiChJoxEO5EuviXpz', '1c3919b2-43ca-4a4a-935d-9d50135ec0ef')
    all_artists_list.append(afi)

    alice_cooper = Artist('Alice Cooper', '3EhbVgyfGd7HkpsagwL9GS', '4d7928cd-7ed2-4282-8c29-c0c9f966f1bd')
    all_artists_list.append(alice_cooper)

    alkaline_trio = Artist('Alkaline Trio', '1aEYCT7t18aM3VvM6y8oVR', '69421e11-e4c3-4854-951b-ceab4972e38e')
    all_artists_list.append(alkaline_trio)

    animals_as_leaders = Artist('Animals as Leaders', '65C6Unk7nhg2aCnVuAPMo8', '5c2d2520-950b-4c78-84fc-78a9328172a3')
    all_artists_list.append(animals_as_leaders)

    architects = Artist('Architects', '3ZztVuWxHzNpl0THurTFCv', '05dffdbe-dc6e-4c8d-a075-50a09c4cb45c')
    all_artists_list.append(architects)

    asking_alexandria = Artist('Asking Alexandria', '1caBfBEapzw8z2Qz9q0OaQ', '9d2fde91-4633-430d-87f0-2b9bbb7fa451')
    all_artists_list.append(asking_alexandria)

    atreyu = Artist('Atreyu', '3LkSiHbjqOHCKCqBfEZOTv', '17e137fb-59e5-4fd7-af48-afc34995396c')
    all_artists_list.append(atreyu)

    attila = Artist('Attila', '4Uv5bceTJ2h3tLlssUNDNP', 'f0b1619b-6b76-4633-9a83-85b11a17ad98')
    all_artists_list.append(attila)

    avenged_sevenfold = Artist('Avenged Sevenfold', '0nmQIMXWTXfhgOBdNzhGOs', '24e1b53c-3085-4581-8472-0b0088d2508c')
    all_artists_list.append(avenged_sevenfold)

    bearings = Artist('Bearings', '0qpDBxRgLp6g0k2esJlUDn', '5a19c7e6-b435-45f4-b1de-2db9b3271cc5')
    all_artists_list.append(bearings)

    beartooth = Artist('Beartooth', '6vwjIs0tbIiseJMR3pqwiL', '98a1e0ab-35fa-40dd-b62c-9fda46fdb061')
    all_artists_list.append(beartooth)

    being_as_an_ocean = Artist('Being as an Ocean', '7ML9AQvVVE3c5m0sx1PlmP', '956f5b24-6734-4d4d-94f2-411113485736')
    all_artists_list.append(being_as_an_ocean)

    belmont = Artist('Belmont', '6hxiY0CFXTibGUtp8TdCxp', '325afbbe-68eb-4938-9186-f6869e64c7b4')
    all_artists_list.append(belmont)

    between_you_and_me = Artist('Between You & Me', '1P1y4wp6V0CwjhGcXPKgAu', 'a4dbddc8-a08d-424e-b0b7-69b423681190')
    all_artists_list.append(between_you_and_me)

    between_the_buried_and_me = Artist('Between the Buried and Me', '2JC4hZm1egeJDEolLsMwZ9',
                                       '1870fb43-50f1-4660-a879-bb596d1519b6')
    all_artists_list.append(between_the_buried_and_me)

    blessthefall = Artist('Blessthefall', '7t2C8WwLyKUKRe0LVh8zl9', 'aafa70a4-2f06-4975-935e-b283fc87de7e')
    all_artists_list.append(blessthefall)

    blvckceiling = Artist('BLVCK CEILING', '0jpfFJygOanIxOrI719zY5', '00b1ccfb-0e26-4b8d-9124-f1c88370149f')
    all_artists_list.append(blvckceiling)

    born_of_osiris = Artist('Born of Osiris', '4HgqjpBaWctBWVHafQIpRt', '132ca1ea-0891-420f-b129-50247bb144b5')
    all_artists_list.append(born_of_osiris)

    boston_manor = Artist('Boston Manor', '4WjeQi9wm84lYTIWZ95QoM', 'cd584ea0-0fc5-412b-8598-0244c4025af6')
    all_artists_list.append(boston_manor)

    breaking_benjamin = Artist('Breaking Benjamin', '5BtHciL0e0zOP7prIHn3pP', '854a1807-025b-42a8-ba8c-2a39717f1d25')
    all_artists_list.append(breaking_benjamin)

    buckcherry = Artist('Buckcherry', '0yN7xI1blow9nYIK0R8nM7', '822e92ef-72ea-42e0-9af1-b987816b487a')
    all_artists_list.append(buckcherry)

    butcher_babies = Artist('Butcher Babies', '6FcvjJzvxgybo7Ywsj0hRj', 'e43b7e0e-0927-4a66-8cd4-8a6bfb162bd8')
    all_artists_list.append(butcher_babies)

    chelsea_grin = Artist('Chelsea Grin', '4UgQ3EFa8fEeaIEg54uV5b', 'b0acce58-e847-4c9e-bd09-a204b965e74a')
    all_artists_list.append(chelsea_grin)

    chevelle = Artist('Chevelle', '56dO9zeHKuU5Gvfc2kxHNw', '8456e9f7-debf-4579-a86c-33a325a35d2d')
    all_artists_list.append(chevelle)

    the_contortionist = Artist('The Contortionist', '7nCgNmfYJcsVy3vOOzExYS', 'a630b133-bcc4-4796-9a0e-685c68b1e6ab')
    all_artists_list.append(the_contortionist)

    counterparts = Artist('Counterparts', '5LyRnL0rysObxDRxzSfV1z', '4b0dd5e7-c795-42bd-8311-bc9f71fabd0a')
    all_artists_list.append(counterparts)

    crosses = Artist('Crosses', '3gPZCcrc8KG2RuVl3rtbQ2', '7a10215e-b32f-4b77-b9cc-d90531a3968f')
    all_artists_list.append(crosses)

    crown_the_empire = Artist('Crown the Empire', '2vKiJjsgjgqIECUyYeIVvO', '5cf3bae7-166f-44c2-b48f-63ddea9d4fb2')
    all_artists_list.append(crown_the_empire)

    da_baby = Artist('DaBaby', '4r63FhuTkUYltbVAg5TQnk', '87ae83df-6173-40cc-a0f2-bad543faa6aa')
    all_artists_list.append(da_baby)

    demrick = Artist('Demrick', '3hEgzEeaZ0hb3UXx1U1JRR', 'e20f2448-8e4e-4625-8881-9da8dbe9df24')
    all_artists_list.append(demrick)

    devin_townsend_project = Artist('Devin Townsend Project', '54Xuca1P5nDqfKYZGDfHxl',
                                    'b00cb756-0259-4a50-bbcb-ad22186c5518')
    all_artists_list.append(devin_townsend_project)

    the_dillinger_escape_plan = Artist('The Dillinger Escape Plan', '7IGcjaMGAtsvKBLQX26W4i',
                                       '1bc41dff-5397-4c53-bb50-469d2c277197')
    all_artists_list.append(the_dillinger_escape_plan)

    disturbed = Artist('Disturbed', '3TOqt5oJwL9BE2NG9MEwDa', '4bb4e4e4-5f66-4509-98af-62dbb90c45c5')
    all_artists_list.append(disturbed)

    escape_the_fate = Artist('Escape the Fate', '5ojhEavq6altxW8fWIlLum', 'b9ca7096-68de-455f-8a36-1f1ebb2abf2a')
    all_artists_list.append(escape_the_fate)

    every_time_i_die = Artist('Every Time I Die', '0o7WWONtleH6PWLn5GIoCM', 'ef90f210-f136-4386-ab37-8c00d04eeace')
    all_artists_list.append(every_time_i_die)

    expire = Artist('Expire', '4AfTOzBubFP6STibJPTxwt', '498e46e2-59c9-4320-8ccf-12c67a29b125')
    all_artists_list.append(expire)

    fall_out_boy = Artist('Fall Out Boy', '4UXqAaa6dQYAk18Lv7PEgX', '516cef4d-0718-4007-9939-f9b38af3f784')
    all_artists_list.append(fall_out_boy)

    fit_for_a_king = Artist('Fit for a King', '0OgdRTPItr9dw4XYp4JJUx', '6eaab7b4-f2cb-4c80-9b36-7e7d5c2fa8c5')
    all_artists_list.append(fit_for_a_king)

    five_finger_death_punch = Artist('Five Finger Death Punch', '5t28BP42x2axFnqOOMg3CM',
                                     '7e8571b1-7c5a-4739-bc51-73d422ee9d74')
    all_artists_list.append(five_finger_death_punch)

    the_ghost_inside = Artist('The Ghost Inside', '6kQB2RN7WwryMdJ1MoQh1E', '6fbd58c3-e9b3-4419-a197-0a0f22baed94')
    all_artists_list.append(the_ghost_inside)

    grayscale = Artist('Grayscale', '6Xq9CIMYWK4RCrMVtfEOM0', '38fab396-e3a8-4538-ba80-dd5eedf40e39')
    all_artists_list.append(grayscale)

    halestorm = Artist('Halestorm', '6om12Ev5ppgoMy3OYSoech', 'eaed2193-e026-493b-ac57-113360407b06')
    all_artists_list.append(halestorm)

    hands_like_houses = Artist('Hands Like Houses', '0u3d5PM2FuEuG5QuUdt8mT', '5f4ad442-76d1-4cd3-8677-3cff7be4c8d4')
    all_artists_list.append(hands_like_houses)

    harms_way = Artist('Harm’s Way', '4ZycjRroJpEHjKMxs8zsek', '70d9fdd1-7c7e-4dfd-be7a-8f606a71c9a2')
    all_artists_list.append(harms_way)

    heavens_basement = Artist('Heaven’s Basement', '6NNdk5EWspD36uNyLZ1Yz8', 'c2c4d56a-d599-4a18-bd2f-ae644e2198cc')
    all_artists_list.append(heavens_basement)

    hed_pe = Artist('(həd) p.e.', '0xIChbcTsuYLueN1oEsX9v', '19516266-e5d9-4774-b749-812bb76a6559')
    all_artists_list.append(hed_pe)

    hinder = Artist('Hinder', '6BMhCQJYHxxKAeqYS1p5rY', '39b22a9e-59dd-412b-ac3c-0725c807c72b')
    all_artists_list.append(hinder)

    hollywood_undead = Artist('Hollywood Undead', '0CEFCo8288kQU7mJi25s6E', '321fdfbb-426b-43f7-8295-fa9aca6348d9')
    all_artists_list.append(hollywood_undead)

    homesafe = Artist('Homesafe', '5vV4gEs3O35SdrdwhvhYwe', '70599552-0c12-4cbf-a793-8033cbb4efc0')
    all_artists_list.append(homesafe)

    hundredth = Artist('Hundredth', '2rtsR8zno5naTxY0iJr7M0', '66b2f925-e924-4cde-b09f-27ec21d29564')
    all_artists_list.append(hundredth)

    ill_nino = Artist('Ill Niño', '1xJ6l1VXgGuyZ0uhu27caF', '91e2e08f-abd7-44d6-9a84-b8a4afa8a265')
    all_artists_list.append(ill_nino)

    in_this_moment = Artist('In This Moment', '6tbLPxj1uQ6vsRQZI2YFCT', '29266b3d-b5ae-4d09-b721-326246adf68f')
    all_artists_list.append(in_this_moment)

    i_prevail = Artist('I Prevail', '3Uobr6LgQpBbk6k4QGAb3V', '1921c28c-ec61-4725-8e35-38dd656f7923')
    all_artists_list.append(i_prevail)

    kiss = Artist('KISS', '07XSN3sPlIlB2L2XNcTwJw', 'e1f1e33e-2e4c-4d43-b91b-7064068d3283')
    all_artists_list.append(kiss)

    kittie = Artist('Kittie', '0ImEDe9tW5n4pxHOK39zIc', '7677be48-16e9-4c84-9365-a69dd6f2df55')
    all_artists_list.append(kittie)

    knocked_loose = Artist('Knocked Loose', '4qrHkx5cgWIslciLXUMrYw', '9ca10859-49e2-44e3-b3d6-04c535207bc2')
    all_artists_list.append(knocked_loose)

    korn = Artist('Korn', '3RNrq3jvMZxD9ZyoOZbQOD', 'ac865b2e-bba8-4f5a-8756-dd40d5e39f46')
    all_artists_list.append(korn)

    like_pacific = Artist('Like Pacific', '5VKmfBc2pR80IxYoC1gHyH', 'b697ecde-c617-4e7a-9032-41e2235d6db6')
    all_artists_list.append(like_pacific)

    limp_bizkit = Artist('Limp Bizkit', '165ZgPlLkK7bf5bDoFc6Sb', '8f9d6bb2-dba4-4cca-9967-cc02b9f4820c')
    all_artists_list.append(limp_bizkit)

    machine_gun_kelly = Artist('Machine Gun Kelly', '6TIYQ3jFPwQSRmorSezPxX', 'f6af669a-56ea-448a-a044-de76181ada33')
    all_artists_list.append(machine_gun_kelly)

    mastodon = Artist('Mastodon', '1Dvfqq39HxvCJ3GvfeIFuT', 'bc5e2ad6-0a4a-4d90-b911-e9a7e6861727')
    all_artists_list.append(mastodon)

    memphis_may_fire = Artist('Memphis May Fire', '7cNNNhdJDrt3vgQjwSavNf', '681b5ab2-b7dd-4dff-85e9-1e84503ad36a')
    all_artists_list.append(memphis_may_fire)

    motionless_in_white = Artist('Motionless in White', '6MwPCCR936cYfM1dLsGVnl',
                                 '1c5b9bd6-76e8-4fe7-a6df-3bc0b5a452cc')
    all_artists_list.append(motionless_in_white)

    motley_crue = Artist('Motley Crue', '0cc6vw3VN8YlIcvr1v7tBL', '26f07661-e115-471d-a930-206f5c89d17c')
    all_artists_list.append(motley_crue)

    movements = Artist('Movements', '1kkyfIopIiVvaPHHlbsfac', '051f5167-0c74-4339-87b5-5e84f5a7469d')
    all_artists_list.append(movements)

    neck_deep = Artist('Neck Deep', '2TM0qnbJH4QPhGMCdPt7fH', 'c41dd59f-d805-41df-9e0e-83ec0f9f468e')
    all_artists_list.append(neck_deep)

    niall_horan = Artist('Niall Horan', '1Hsdzj7Dlq2I7tHP7501T4', '55e6074f-ef78-4ec3-8fff-bd1b8cc8c14a')
    all_artists_list.append(niall_horan)

    nonpoint = Artist('Nonpoint', '6BdSOHfQ6kMg0tbAFlXR1z', 'f10177e4-b7f7-4e63-92b6-c805c6cc54d6')
    all_artists_list.append(nonpoint)

    norma_jean = Artist('Norma Jean', '55b0Gfm53udtGBs8mmNXrH', 'a02b1a45-271c-4bc3-9d82-68bb896cb5fd')
    all_artists_list.append(norma_jean)

    ozzy_osbourne = Artist('Ozzy Osbourne', '6ZLTlhejhndI4Rh53vYhrY', '8aa5b65a-5b3c-4029-92bf-47a544356934')
    all_artists_list.append(ozzy_osbourne)

    papa_roach = Artist('Papa Roach', '4RddZ3iHvSpGV4dvATac9X', 'c5eb9407-caeb-4303-b383-6929aa94021c')
    all_artists_list.append(papa_roach)

    periphery = Artist('Periphery', '6d24kC5fxHFOSEAmjQPPhc', 'a0cef17a-4574-44f4-9f97-fd068615dac6')
    all_artists_list.append(periphery)

    pierce_the_veil = Artist('Pierce the Veil', '4iJLPqClelZOBCBifm8Fzv', '8ed919fb-eaee-45a1-ba99-b3ede9ca5f1d')
    all_artists_list.append(pierce_the_veil)

    poison = Artist('Poison', '1fBCIkoPOPCDLUxGuWNvyo', 'c79c43d4-cbed-4373-89ce-6560f62eb7d8')
    all_artists_list.append(poison)

    the_porkers = Artist('The Porkers', '4vBYqviD5QVXMsNO4Y2EdL', '5026623c-28bf-46ab-a7b5-aed151282b01')
    all_artists_list.append(the_porkers)

    the_raskins = Artist('The Raskins', '44ujCYzu2TnXjBWVihoM7P', '63e164b9-f06a-47f5-9ebe-6887ddd4539c')
    all_artists_list.append(the_raskins)

    real_friends = Artist('Real Friends', '6dEtLwgmSI0hmfwTSjy8cw', '9ac8bee0-1c34-46c6-9eee-ee1eb96df282')
    all_artists_list.append(real_friends)

    rich_people = Artist('Rich People', '5lSyekL7APqKdusY0pGcGf', 'e00e1673-2e60-4e5d-81af-231c2a860d52')
    all_artists_list.append(rich_people)

    scorpions = Artist('Scorpions', '27T030eWyCQRmDyuvr1kxY', 'c3cceeed-3332-4cf0-8c4c-bbde425147b6')
    all_artists_list.append(scorpions)

    seether = Artist('Seether', '6B5c4sch27tWHAGdarpPaW', 'fbcd7b29-455f-49e6-9c4f-8249d20a055e')
    all_artists_list.append(seether)

    set_it_off = Artist('Set It Off', '06bDwgCHeMAwhgI8il4Y5k', '823ed9ad-3412-47dc-9caf-b7be02121fcf')
    all_artists_list.append(set_it_off)

    sevendust = Artist('Sevendust', '35Uu85Pq33mK8x1jYqsHY2', '52b9e109-44a0-45eb-a197-226c4abab232')
    all_artists_list.append(sevendust)

    shinedown = Artist('Shinedown', '70BYFdaZbEKbeauJ670ysI', 'adc0f033-95c2-4e0b-87bc-c23ed3f26ce6')
    all_artists_list.append(shinedown)

    silverstein = Artist('Silverstein', '1Tsag5J854qxeOo2apszug', 'd89de379-665d-425c-b2e9-41b95d1edb36')
    all_artists_list.append(silverstein)

    sleep_on_it = Artist('Sleep On It', '5FmgqLlJ8MJ9A8zmOPFxK2', '687823ac-a3b3-495c-bb20-68bce137c77d')
    all_artists_list.append(sleep_on_it)

    sleeping_with_sirens = Artist('Sleeping With Sirens', '3N8Hy6xQnQv1F1XCiyGQqA',
                                  '3267d5a3-c72c-4c3b-bafe-ec8a569c0b74')
    all_artists_list.append(sleeping_with_sirens)

    slipknot = Artist('Slipknot', '05fG473iIaoy82BF1aGhL8', 'a466c2a2-6517-42fb-a160-1087c3bafd9f')
    all_artists_list.append(slipknot)

    state_champs = Artist('State Champs', '1qqdO7xMptucPDMopsOdkr', 'e2e9df76-a950-4b8b-b3d1-981624470657')
    all_artists_list.append(state_champs)

    stick_to_your_guns = Artist('Stick to Your Guns', '2sqrupqcoipb7UzVKApEnJ', '07ef6bdd-20c8-4f2b-ac87-463f65b90768')
    all_artists_list.append(stick_to_your_guns)

    stone_sour = Artist('Stone Sour', '49qiE8dj4JuNdpYGRPdKbF', '4ca783b7-5bf7-4348-b494-46680660050f')
    all_artists_list.append(stone_sour)

    sum41 = Artist('Sum 41', '0qT79UgT5tY4yudH9VfsdT', 'f2eef649-a6d5-4114-afba-e50ab26254d2')
    all_artists_list.append(sum41)

    sylar = Artist('Sylar', '78vP5COn64VXULgkIQovEA', 'd164d8e4-f505-4ed8-9345-c0bd1fa67ccc')
    all_artists_list.append(sylar)

    taproot = Artist('Taproot', '319rafipfKvd4cqaOwWIvA', '05851234-4e8f-4cc8-b682-a55c23277d9c')
    all_artists_list.append(taproot)

    three_days_grace = Artist('Three Days Grace', '2xiIXseIJcq3nG7C8fHeBj', 'fabb37f8-eb2a-4cc1-a72a-b56935bbb72d')
    all_artists_list.append(three_days_grace)

    veil_of_maya = Artist('Veil of Maya', '2i7CQcVBh2K6uOR3CH09M1', '32e740e5-95ea-42e3-b5e2-29f6630488e4')
    all_artists_list.append(veil_of_maya)

    vukovi = Artist('VUKOVI', '1844Ua6R4gOuH6GLdlR4dt', '159495a4-0f57-4739-b34c-f16bb770e191')
    all_artists_list.append(vukovi)

    warrant = Artist('Warrant', '7HLvzuM9p11k9lUQfSM4Rq', '9aa0d535-3efe-468c-afda-43bd17d44641')
    all_artists_list.append(warrant)

    waysted = Artist('Waysted', '42ueAipELI8IvTUa9gN50Q', '05504d00-67ea-40bd-ae98-0a96d0d42d6a')
    all_artists_list.append(waysted)

    whitesnake = Artist('Whitesnake', '3UbyYnvNIT5DFXU4WgiGpP', '5dedf5cf-a598-4408-9556-3bf3f149f3ba')
    all_artists_list.append(whitesnake)

    young_thug = Artist('Young Thug', '50co4Is1HCEo8bhOyUWKpn', '800760de-bdf8-43a2-8fe0-44a2401a5515')
    all_artists_list.append(young_thug)

    artist_id_cross_reference = {}
    for i in range(0, len(all_artists_list)):
        artist_id_cross_reference[all_artists_list[i].name] = all_artists_list[i]
    return artist_id_cross_reference
