import streamlit as st
import pandas as pd
import folium
from folium.plugins import MarkerCluster
import requests
import xml.etree.ElementTree as ET
from streamlit_folium import folium_static
import datetime
from dateutil.relativedelta import relativedelta
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
import json
import numpy as np
import time
from pycaret.classification import load_model
from streamlit_extras.mandatory_date_range import date_range_picker
from streamlit_extras.no_default_selectbox import selectbox
from streamlit_extras.switch_page_button import switch_page

st.set_page_config(
    page_title="Pelampung.AI",
    page_icon="images/logo-small.png",
    layout="centered",
)

kode_cuaca = {
    0: "☀️",  # Cerah / Clear Skies
    1: "⛅",   # Cerah Berawan / Partly Cloudy
    2: "⛅",   # Cerah Berawan / Partly Cloudy
    3: "☁️",  # Berawan / Mostly Cloudy
    4: "☁️",  # Berawan Tebal / Overcast
    5: "🌫️",  # Udara Kabur / Haze
    10: "🌫️", # Asap / Smoke
    45: "🌁",  # Kabut / Fog
    60: "🌧️", # Hujan Ringan / Light Rain
    61: "🌧️", # Hujan Sedang / Rain
    63: "⛈️",  # Hujan Lebat / Heavy Rain
    80: "🌦️", # Hujan Lokal / Isolated Shower
    95: "🌩️", # Hujan Petir / Severe Thunderstorm
    97: "🌩️", # Hujan Petir / Severe Thunderstorm
}

@st.cache_data
# Fungsi untuk mengambil data BMKG
def get_bmkg_data():
    url =  'https://data.bmkg.go.id/DataMKG/MEWS/DigitalForecast/DigitalForecast-Indonesia.xml'
    text = requests.get(url).text
    root = ET.fromstring(text)

    columns = ['area_id', 'lat', 'long', 'coord', 'type','description','param_id','param_description','param_type','timerange_type', 'timerange_datetime','value','unit']
    df_areas = pd.DataFrame(columns=columns)
    
    for areas in root:
        for area in areas:
            if area.tag == 'area':
                area_id, lat, long, coord, type, description = area.attrib['id'],area.attrib['latitude'],area.attrib['longitude'], area.attrib['coordinate'], area.attrib['type'],area.attrib['description']
                print(60*'=')
                print(f'{area_id}\t{description}\nLat, Long: {lat},{long}\nCoordinate: {coord}')
                print(60*'=')
                for params in area:
                    if params.tag == 'parameter':
                        param_id, param_description,param_type = params.attrib['id'], params.attrib['description'], params.attrib['type']
                        print(f'{param_id} {param_description}({param_type})')
                        print(60*'=')
                        for timerange in params:
                            timerange_type, timerange_datetime = timerange.attrib['type'],timerange.attrib['datetime']
                            datedate,mondate,yeardate= timerange_datetime[6:8], timerange_datetime[4:6],timerange_datetime[:4]
                            hourdate, mindate = timerange_datetime[8:10], timerange_datetime[10:]
                            tgl = f'{datedate}-{mondate}-{yeardate} {hourdate}:{mindate}'
                            for value in timerange:
                                if description == 'Weather':
                                    value.text = kode_cuaca[int(value.text)]
                                new_row = pd.Series({'area_id':area_id, 'lat':lat, 'long':long, 'coord':coord, 'type':type, 'description':description,
                                                    'param_id':param_id, 'param_description':param_description,'param_type':param_type,
                                                    'timerange_type':timerange_type, 'timerange_datetime':timerange_datetime,
                                                    'value':value.text,'unit':value.attrib['unit'] })
                                df_areas = pd.concat([df_areas,new_row.to_frame().T],ignore_index=True)
                                print(tgl, value.text,value.attrib['unit'])
                                break
                        print(60*'=')
                    else:
                        pass
            else:
                pass
            print("")

    df = df_areas.copy()
    df = df[['lat', 'long','description', 'param_id','param_type','timerange_datetime', 'value']]
    df.rename(columns={'lat': 'latitude', 'long': 'longitude', 'description': 'kabupaten', 'param_id': 'parameter', 'param_type': 'tipe', 'timerange_datetime': 'tanggal'}, inplace=True)
    df['tanggal'] = df['tanggal'].astype('str')
    df['tanggal'] = df['tanggal'].str[:8]
    df.rename(columns={'value': 'nilai'}, inplace=True)
    df['tanggal'] = pd.to_datetime(df['tanggal'], format='%Y%m%d')
    hourly_data = df[df['tipe'] == 'hourly']
    hourly_data['tanggal'] = pd.to_datetime(hourly_data['tanggal'])
    hourly_data['nilai'] = hourly_data['nilai'].astype(float)
    daily_data = hourly_data.groupby(['latitude', 'longitude', 'kabupaten', 'parameter', pd.Grouper(key='tanggal', freq='D')])['nilai'].mean().reset_index()
    unique_parameters = ['humax', 'tmax', 'humin', 'tmin']
    df = df.drop(columns='tipe')
    daily_data = daily_data.append(df[df['parameter'].isin(unique_parameters)])
    daily_data.reset_index(drop=True, inplace=True)
    
    return daily_data

# Fungsi untuk mengambil data kejadian banjir
def get_flood_data():
    data_bencana_bnpb_path = "database/data_bencana_bnpb.xlsx"
    flood_data = pd.read_excel(data_bencana_bnpb_path)
    return flood_data

# Halaman utama
def show_dashboard():
    st.image("images/logo.png", width=350)
    st.title("📊 Dashboard")
    
    # Ambil data BMKG
    bmkg_data = get_bmkg_data()

    st.subheader("Data Cuaca")
    # Tampilkan pilihan kabupaten
    kabupaten_list = sorted(bmkg_data['kabupaten'].unique())
    selected_kabupaten = selectbox("Pilih Kabupaten/Kota", kabupaten_list, no_selection_label="Kabupaten/Kota")
    
    if selected_kabupaten is None:
        st.info("Silakan pilih Kabupaten/Kota untuk menampilkan data cuaca")
    else:
        # Filter data berdasarkan kabupaten yang dipilih
        selected_data = bmkg_data[bmkg_data['kabupaten'] == selected_kabupaten]

        # Filter data untuk hari ini
        today = datetime.date.today()
        selected_data_today = selected_data[selected_data['tanggal'].dt.date == today]

        # Filter data untuk besok
        tomorrow = today + datetime.timedelta(days=1)
        selected_data_tomorrow = selected_data[selected_data['tanggal'].dt.date == tomorrow]

        # Membuat tab
        tabs = st.tabs(["Hari Ini", "Besok"])

        # Tab Hari Ini
        with tabs[0]:
            st.subheader("Cuaca Hari Ini")
            col1, col2, col3 = st.columns(3)

            if not selected_data_today.empty:
                metrics = {
                    't': ("🌡️Suhu (°C)", "°C"),
                    'tmax': ("🔺Suhu Maksimum (°C)", "°C"),
                    'tmin': ("🔻Suhu Minimum (°C)", "°C"),
                    'hu': ("💧Kelembapan (%)", "%"),
                    'humax': ("🔺Kelembapan Maksimum (%)", "%"),
                    'humin': ("🔻Kelembapan Minimum (%)", "%"),
                    'weather': ("🖼️Cuaca", ""),
                    'wd': ("🧭Arah Angin (°)", "°"),
                    'ws': ("🍃Kecepatan Angin (m/s)", "m/s")
                }

                for parameter, (label, unit) in metrics.items():
                    value = selected_data_today[selected_data_today['parameter'] == parameter]['nilai'].values[0]
                    formatted_value = f"{value} {unit}" if unit else str(value)
                    if parameter in ['weather']:
                        formatted_value = kode_cuaca.get(value, "Tidak Diketahui")
                    if parameter in ['t', 'tmax', 'tmin']:
                        col1.metric(label, formatted_value)
                    elif parameter in ['hu', 'humax', 'humin']:
                        col2.metric(label, formatted_value)
                    else:
                        col3.metric(label, formatted_value)
                st.write("Sumber data: BMKG")

            else:
                st.write("Data cuaca untuk hari ini tidak tersedia.")

        # Tab Besok
        with tabs[1]:
            st.subheader("Cuaca Besok")
            col1, col2, col3 = st.columns(3)

            if not selected_data_tomorrow.empty:
                metrics = {
                    't': ("🌡️Suhu (°C)", "°C"),
                    'tmax': ("🔺Suhu Maksimum (°C)", "°C"),
                    'tmin': ("🔻Suhu Minimum (°C)", "°C"),
                    'hu': ("💧Kelembapan (%)", "%"),
                    'humax': ("🔺Kelembapan Maksimum (%)", "%"),
                    'humin': ("🔻Kelembapan Minimum (%)", "%"),
                    'weather': ("🖼️Cuaca", ""),
                    'wd': ("🧭Arah Angin (°)", "°"),
                    'ws': ("🍃Kecepatan Angin (m/s)", "m/s")
                }

                for parameter, (label, unit) in metrics.items():
                    value = selected_data_tomorrow[selected_data_tomorrow['parameter'] == parameter]['nilai'].values[0]
                    formatted_value = f"{value} {unit}" if unit else str(value)
                    if parameter in ['weather']:
                        formatted_value = kode_cuaca.get(value, "Tidak Diketahui")
                    if parameter in ['t', 'tmax', 'tmin']:
                        col1.metric(label, formatted_value)
                    elif parameter in ['hu', 'humax', 'humin']:
                        col2.metric(label, formatted_value)
                    else:
                        col3.metric(label, formatted_value)
                st.write("Sumber data: BMKG")

            else:
                st.write("Data cuaca untuk besok tidak tersedia.")
        
    # Tampilkan peta history kejadian banjir
    st.subheader("Peta Kejadian Banjir di Indonesia (2003-2023)")
    flood_data = get_flood_data()
    years = sorted(flood_data['tahun'].unique())
    selected_year = st.slider("Pilih Rentang Tahun", min_value=int(min(years)), max_value=int(max(years)), value=(2023, 2023))

    filtered_data = flood_data[(flood_data['tahun'] >= selected_year[0]) & (flood_data['tahun'] <= selected_year[1])]
    map = folium.Map(location=[-2.5489, 118.0149], zoom_start=4)

    cluster_banjir = MarkerCluster(name='Banjir').add_to(map)
    for index, row in filtered_data.iterrows():
        lat = row['latitude']
        lon = row['longitude']
        popup = f"Tanggal: {row['tanggal']}\nMeninggal: {row['Meninggal']}\nHilang: {row['Hilang']}\nTerluka: {row['Terluka']}\nMenderita: {row['Menderita']}\nMengungsi: {row['Mengungsi']}\nRumah: {row['Rumah']}\nFas_Pendidikan: {row['Fas_Pendidikan']}\nFas_Kesehatan: {row['Fas_Kesehatan']}\nFas_Peribadatan: {row['Fas_Peribadatan']}\nFas_Umum: {row['Fas_Umum']}\nPerkantoran: {row['Perkantoran']}\nJembatan: {row['Jembatan']}\nPabrik: {row['Pabrik']}\nPertokoan: {row['Pertokoan']}"
        folium.Marker(location=[lat, lon], popup=popup).add_to(cluster_banjir)

    folium.LayerControl().add_to(map)
    # Tampilkan peta dalam Streamlit
    folium_static(map)
    st.write("Sumber data: BNPB")

    col1, col2 = st.columns(2)

    with col1:
        # Grafik batang jumlah kejadian banjir pada tahun terpilih
        st.subheader("Kejadian Banjir per Provinsi Tahun " + str(selected_year))
        top_provinces = filtered_data[filtered_data['banjir'] == 1]['provinsi'].value_counts().sort_values(ascending=True)
        st.bar_chart(top_provinces)
        st.write("Sumber data: BNPB")

    with col2:
        # Filter data for banjir parameter
        tren_banjir = flood_data[flood_data['banjir'] == 1]
        flood_counts = tren_banjir['tahun'].value_counts().sort_index()

        # Display trend chart of flood occurrences
        st.subheader('Grafik Kejadian Banjir di Indonesia (2003-2023)')
        st.line_chart(data=flood_counts, use_container_width=True)
        st.write("Sumber data: BNPB")

RESOLUTIONS = ["hourly", "daily", "monthly", "climatology"]
COMMUNITIES = ["RE", "SB", "AG"]

def point(
    *, coordinates, parameters, start, end, resolution="daily", community="RE",
):
    # Validate and parse the coordinates
    if pd.api.types.is_list_like(coordinates):
        if len(coordinates) != 2:
            raise ValueError("Coordinate list should have 2 values")
        latitude, longitude = coordinates
    if isinstance(coordinates, dict):
        if "lat" not in coordinates:
            raise ValueError("Coordinates does not contain a 'lat' key")
        if "lon" not in coordinates.index:
            raise ValueError("Coordinates does not contain a 'lon' key")
        latitude = coordinates["lat"]
        longitude = coordinates["lon"]
    if isinstance(coordinates, pd.core.series.Series):
        if "lat" not in coordinates.index:
            raise ValueError("Coordinates does not have 'lat' in index")
        if "lat" not in coordinates.index:
            raise ValueError("Coordinates does not have 'lat' in index")
        latitude = coordinates["lat"]
        longitude = coordinates["lon"]
    if not isinstance(latitude, int) and not isinstance(latitude, float):
        raise TypeError("Latitude should be an integer or float")
    if not isinstance(longitude, int) and not isinstance(longitude, float):
        raise TypeError("Longitude should be an integer or float")
    if not isinstance(latitude, (int, float, str, np.number)):
        raise TypeError("Latitude should be a number")
    if not isinstance(longitude, (int, float, str, np.number)):
        raise TypeError("Longitude should be a number")
    if latitude < -90 or latitude > 90:
        raise ValueError("Latitude should be between -90 and 90")
    if longitude < 0 or longitude > 360:
        raise ValueError("Longitude should be between 0 and 360")

    # Validate the community
    if community not in COMMUNITIES:
        raise ValueError(f"Community should be one of {COMMUNITIES}")

    # Validate the parameters
    if not isinstance(parameters, list):
        raise TypeError("Parameters should be a list")

    # Validate the resolution
    if resolution not in RESOLUTIONS:
        raise TypeError(f"Resolution should be one of {RESOLUTIONS}")

    # Validate the start and end date
    if resolution in ["hourly", "daily"]:
        if not isinstance(start, (datetime.datetime, datetime.date)):
            raise TypeError("Start should be a datetime or date")
        if not isinstance(end, (datetime.datetime, datetime.date)):
            raise TypeError("End should be a datetime or date")
        if start < datetime.date(1982, 1, 1) or start > datetime.date.today():
            raise ValueError("Start should be between 1982 and today")
        if end < datetime.date(1982, 1, 1) or end > datetime.date.today():
            raise ValueError("End should be between 1982 and today")
        if start > end:
            raise ValueError("Start must be before end")
    else:
        if not isinstance(start, int):
            raise TypeError("Start should be an integer")
        if not isinstance(start, int):
            raise TypeError("End should be an integer")
        if start < 1982 or start > 2020:
            raise ValueError("Start should be between 1982 and 2020")
        if end < 1982 or end > 2020:
            raise ValueError("End should be between 1982 and 2020")
        if start > end:
            raise ValueError("Start must be before end")

    # Retrieve the data
    try:
        url = f"https://power.larc.nasa.gov/api/temporal/{resolution}/point"
        params = {
            "parameters": ",".join(parameters),
            "longitude": longitude,
            "latitude": latitude,
            "start": start.strftime("%Y%m%d"),
            "end": end.strftime("%Y%m%d"),
            "community": community,
            "format": "JSON",
        }
        response = requests.get(url=url, params=params, verify=True, timeout=60)
        content = json.loads(response.content.decode("utf-8"))
    except:
        raise Exception(f"Could not fetch the data")

    # Check if there are any error messages
    if len(content.get("messages", [])) > 0:
        raise Exception(content["messages"][0])

    # Check if there are any other error messages
    details = content.get("detail", [])
    if len(details):
        raise Exception(details[0].get("msg"))

    # Transform the data into a DataFrame
    data = pd.DataFrame(content["properties"]["parameter"])
    data.index = pd.to_datetime(data.index, format="%Y%m%d")

    # Return the data
    return data

def get_climate_data(latitude, longitude, tanggal):
    # Ubah tanggal menjadi objek datetime.date
    tanggal_date = datetime.date(tanggal.year, tanggal.month, tanggal.day)

    # Ambil data iklim dari fungsi point
    daily_data = point(
        coordinates=(latitude, longitude),
        parameters=["ALLSKY_SFC_SW_DWN", "ALLSKY_SFC_LW_DWN", "TS", "PRECTOTCORR",
                    "T10M", "T10M_MAX", "T10M_MIN", "WD10M", "WS10M", "WS10M_MAX",
                    "RH2M", "QV2M", 'TQV', 'PS'],
        start=tanggal_date,
        end=tanggal_date,
        resolution="daily",
        community="AG",
    )

    # Buat dictionary untuk menyimpan data iklim
    data_iklim = {
        "ALLSKY_SFC_SW_DWN": daily_data["ALLSKY_SFC_SW_DWN"].values[0],
        "ALLSKY_SFC_LW_DWN": daily_data["ALLSKY_SFC_LW_DWN"].values[0],
        "TS": daily_data["TS"].values[0],
        "PRECTOTCORR": daily_data["PRECTOTCORR"].values[0],
        "T10M": daily_data["T10M"].values[0],
        "T10M_MAX": daily_data["T10M_MAX"].values[0],
        "T10M_MIN": daily_data["T10M_MIN"].values[0],
        "WD10M": daily_data["WD10M"].values[0],
        "WS10M": daily_data["WS10M"].values[0],
        "WS10M_MAX": daily_data["WS10M_MAX"].values[0],
        "RH2M": daily_data["RH2M"].values[0],
        "QV2M": daily_data["QV2M"].values[0],
        "TQV": daily_data["TQV"].values[0],
        "PS": daily_data["PS"].values[0]
    }

    return data_iklim

# Halaman prediksi
def show_prediction_page():
    st.image("images/logo.png", width=350)
    st.title("🔍 Prediksi Banjir")
    
    # Input Lokasi
    location_option = st.radio("Pilih Opsi Input Lokasi", ("Alamat", "Koordinat"))

    if location_option == "Alamat":
        
        st.info("Pilih opsi koordinat jika alamat tidak ditemukan/lokasi tidak valid.")

        provinces = pd.read_csv('database/provinces.csv', header=None)
        regencies = pd.read_csv('database/regencies.csv', header=None)
        districts = pd.read_csv('database/districts.csv', header=None)
        villages = pd.read_csv('database/villages.csv', header=None)

        col1, col2 = st.columns(2)
        with col1:
            selected_province = st.selectbox("Pilih Provinsi", provinces[1].tolist())
            selected_regency = st.selectbox("Pilih Kabupaten/Kota", regencies[2][regencies[1] == provinces[0][provinces[1] == selected_province].values[0]].tolist())
            selected_district = st.selectbox("Pilih Kecamatan", districts[2][districts[1] == regencies[0][regencies[2] == selected_regency].values[0]].tolist())
            selected_village = st.selectbox("Pilih Desa", villages[2][villages[1] == districts[0][districts[2] == selected_district].values[0]].tolist())         

             # Combine the selected location into a single string
            location = f"{selected_village}, {selected_district}, {selected_regency}, {selected_province}"

            try:
                # Geocode the location to get latitude and longitude
                geolocator = Nominatim(user_agent="Pelampung.AI")
                location_data = geolocator.geocode(location)
            except (GeocoderTimedOut, GeocoderServiceError):
                # Handle connection error
                print("Coba lagi: Terjadi kesalahan koneksi. Silakan muat ulang dan coba lagi.")
            
            try:
                if location_data:
                    latitude = location_data.latitude
                    longitude = location_data.longitude

                    st.write("Latitude:", latitude)
                    st.write("Longitude:", longitude)
                else:
                    st.error("Lokasi tidak valid. Silakan pilih lokasi yang lain.")
                    return
            except ValueError:
                # Handle connection error
                print("Coba lagi: Terjadi kesalahan koneksi. Silakan muat ulang dan coba lagi.")

        with col2:
            if location_data is not None:
                # Create a DataFrame with the location data
                location_df = pd.DataFrame({
                    'latitude': [location_data.point.latitude],
                    'longitude': [location_data.point.longitude]
                })

                # Display the map using the DataFrame
                st.map(location_df, zoom=12, use_container_width=True)
            else:
                st.write("Data lokasi tidak tersedia.")
        
    else:  # Koordinat

        st.info("Gunakan [Google Maps](http://maps.google.com/) untuk membantu menemukan latitude dan longitude.")

        col1, col2 = st.columns(2)
        with col1:
            latitude = st.text_input("Latitude")
        with col2:
            longitude = st.text_input("Longitude")

        if not latitude or not longitude:
            st.warning("Silakan isi latitude dan longitude terlebih dahulu.")
        else:
            # Convert latitude and longitude to float format
            try:
                latitude = float(latitude)
                longitude = float(longitude)
            except ValueError:
                st.error("Koordinat tidak valid. Silakan masukkan koordinat yang valid.")
                return

        try:
            geolocator = Nominatim(user_agent="Pelampung.AI")
        except (GeocoderTimedOut, GeocoderServiceError, requests.exceptions.RequestException) as e:
            print("Terjadi kesalahan saat mengambil data lokasi. Silakan coba lagi.")   

        location_data = None
        
        try:
            location_data = geolocator.reverse(f"{latitude}, {longitude}")
        except ValueError:
            st.error("Koordinat tidak valid. Silakan masukkan koordinat yang valid.")
            return

        if location_data:
            address = location_data.address
            st.write("Alamat:", address)
        else:
            st.write("Tidak ada alamat yang ditemukan untuk koordinat tersebut.")
            return

    # Select the machine learning algorithm
    model_option = selectbox("Pilih Algoritma Model", ["LightGBM", "Random Forest", "XGBoost"], no_selection_label='Algoritma')
    st.info("Lihat halaman tutorial untuk memilih model yang sesuai.")

     # Select the date input type
    date_input_type = st.radio("Pilih Jenis Input Tanggal", ["Tanggal Satuan", "Rentang Tanggal"])

    # Single date input
    if date_input_type == "Tanggal Satuan":
        selected_date = st.date_input("Pilih Tanggal")

        # Button to start the prediction process
        if st.button("🔍Prediksi"):
            
            if model_option is None:
                st.error("Silakan pilih model terlebih dahulu")
            else:
                # Show progress bar
                progress_bar = st.progress(0)

                # Show "Mohon menunggu" message
                waiting_message1 = st.info("Mohon menunggu...")
                waiting_message1.empty()

                # Update progress bar and message
                progress_bar.progress(20)
                waiting_message2 = st.info("Mengambil data iklim...")

                tanggal = selected_date
                hari = tanggal.day
                bulan = tanggal.month
                tahun = tanggal.year
                hari_dalam_pekan = tanggal.isoweekday()
                pekan_ke = tanggal.isocalendar()[1]

                # Get the climate data for the specific location and date
                climate_data = get_climate_data(latitude, longitude, tanggal)
                
                waiting_message2.empty()
                
                # Update progress bar and message
                progress_bar.progress(50)
                waiting_message3 = st.info("Mengolah data...")
                
                # Convert 'tanggal' to datetime format
                tanggal = pd.to_datetime(tanggal)

                # Create a DataFrame with the input features
                input_features = pd.DataFrame({
                    'latitude': [latitude],
                    'longitude': [longitude],
                    'tanggal': [tanggal],
                    'hari': [hari],
                    'bulan': [bulan],
                    'tahun': [tahun],
                    'hari_dalam_pekan': [hari_dalam_pekan],
                    'pekan_ke': [pekan_ke],
                    'ALLSKY_SFC_SW_DWN': [climate_data['ALLSKY_SFC_SW_DWN']],
                    'ALLSKY_SFC_LW_DWN': [climate_data['ALLSKY_SFC_LW_DWN']],
                    'TS': [climate_data['TS']],
                    'PRECTOTCORR': [climate_data['PRECTOTCORR']],
                    'T10M': [climate_data['T10M']],
                    'T10M_MAX': [climate_data['T10M_MAX']],
                    'T10M_MIN': [climate_data['T10M_MIN']],
                    'WD10M': [climate_data['WD10M']],
                    'WS10M': [climate_data['WS10M']],
                    'WS10M_MAX': [climate_data['WS10M_MAX']],
                    'RH2M': [climate_data['RH2M']],
                    'QV2M': [climate_data['QV2M']],
                    'TQV': [climate_data['TQV']],
                    'PS': [climate_data['PS']]
                }, index=[0])

                # Load the machine learning model based on the selected option
                if model_option == "LightGBM":
                    model = load_model('models/lgbm_model')
                elif model_option == "Random Forest":
                    model = load_model('models/rf_model')
                elif model_option == "XGBoost":
                    model = load_model('models/xgb_model')

                waiting_message3.empty()

                # Update progress bar and message
                progress_bar.progress(80)
                waiting_message4 = st.info("Melakukan prediksi...")
                
                # Make predictions using the selected model
                pred = model.predict(input_features)

                # Map the prediction to text and emoticon
                pred_text = "Berpotensi banjir" if pred == 1 else "Tidak berpotensi banjir"
                emoticon = "⚠️" if pred == 1 else "✅"

                # Update progress bar and message
                progress_bar.progress(100)
                st.success("Prediksi selesai!")
                
                # Display the prediction result
                st.subheader("Hasil Prediksi")
                st.metric('Potensi Banjir', "{} {}".format(emoticon, pred_text))

                st.subheader("Data Iklim Tanggal {}".format(tanggal.date()))

                col1, col2, col3 = st.columns(3)

                with col1:
                    st.metric("Temperatur Permukaan Bumi", f"{climate_data['TS']} °C")
                    st.metric("Temperatur (10 Meter)", f"{climate_data['T10M']} °C")
                    st.metric("Temperatur Maksimum (10 Meter)", f"{climate_data['T10M_MAX']} °C")
                    st.metric("Temperatur Minimum (10 Meter)", f"{climate_data['T10M_MIN']} °C")
                    st.metric("Kelembaban Relatif (2 Meter)", f"{climate_data['RH2M']} %")

                with col2:
                    st.metric("Kelembaban Spesifik (2 Meter)", f"{climate_data['QV2M']} g/kg")
                    st.metric("Presipitasi", f"{climate_data['PRECTOTCORR']} mm")
                    st.metric("Kadar Air Kolom Jatuh", f"{climate_data['TQV']} mm")
                    st.metric("Radiasi Gelombang Panjang ke Permukaan", f"{climate_data['ALLSKY_SFC_LW_DWN']} W/m²")
                    st.metric("Radiasi Gelombang Pendek ke Permukaan", f"{climate_data['ALLSKY_SFC_SW_DWN']} W/m²")

                with col3:
                    st.metric("Tekanan Permukaan", f"{climate_data['PS']} hPa")
                    st.metric("Arah Angin (10 Meter)", f"{climate_data['WD10M']}°")
                    st.metric("Kecepatan Angin (10 Meter)", f"{climate_data['WS10M']} m/s")
                    st.metric("Kecepatan Angin Maksimum (10 Meter)", f"{climate_data['WS10M_MAX']} m/s")
                st.write("Sumber data: NASA Prediction Of Worldwide Energy Resources")
                waiting_message4.empty()

                # Show refresh button for the page
                if st.button("Reset"):
                    # Refresh the page
                    st.experimental_rerun()
    
    # Date range input
    else:
        date_range = date_range_picker("Pilih Rentang Tanggal")
        selected_start_date = pd.to_datetime(date_range[0])  # Convert to datetime
        selected_end_date = pd.to_datetime(date_range[1])  # Convert to datetime

        # Display the selected date range
        st.write("Rentang Tanggal: ", selected_start_date.date(), " hingga ", selected_end_date.date())

        # Button to start the prediction process for the date range
        if st.button("🔍Prediksi"):
            
            if model_option is None:
                st.error("Silakan pilih model terlebih dahulu")
            else:
                # Show progress bar
                progress_bar = st.progress(0)

                # Show "Mohon menunggu" message
                waiting_message1 = st.info("Mohon menunggu...")
                waiting_message1.empty()

                # Update progress bar and message
                progress_bar.progress(20)
                waiting_message2 = st.info("Mengambil data iklim...")
                
                # Perform prediction for each date in the date range
                prediction_results = []
                
                waiting_message2.empty()

                waiting_message3 = st.info("Melakukan prediksi...")

                # Iterate over each date in the date range
                for single_date in pd.date_range(selected_start_date, selected_end_date):
                    tanggal = single_date.date()
                    hari = tanggal.day
                    bulan = tanggal.month
                    tahun = tanggal.year
                    hari_dalam_pekan = tanggal.isoweekday()
                    pekan_ke = tanggal.isocalendar()[1]

                    # Get the climate data for the specific location and date
                    climate_data = get_climate_data(latitude, longitude, tanggal)

                    # Convert 'tanggal' to datetime format
                    tanggal = pd.to_datetime(tanggal)

                    # Create a DataFrame with the input features
                    input_features = pd.DataFrame({
                        'latitude': [latitude],
                        'longitude': [longitude],
                        'tanggal': [tanggal],
                        'hari': [hari],
                        'bulan': [bulan],
                        'tahun': [tahun],
                        'hari_dalam_pekan': [hari_dalam_pekan],
                        'pekan_ke': [pekan_ke],
                        'ALLSKY_SFC_SW_DWN': [climate_data['ALLSKY_SFC_SW_DWN']],
                        'ALLSKY_SFC_LW_DWN': [climate_data['ALLSKY_SFC_LW_DWN']],
                        'TS': [climate_data['TS']],
                        'PRECTOTCORR': [climate_data['PRECTOTCORR']],
                        'T10M': [climate_data['T10M']],
                        'T10M_MAX': [climate_data['T10M_MAX']],
                        'T10M_MIN': [climate_data['T10M_MIN']],
                        'WD10M': [climate_data['WD10M']],
                        'WS10M': [climate_data['WS10M']],
                        'WS10M_MAX': [climate_data['WS10M_MAX']],
                        'RH2M': [climate_data['RH2M']],
                        'QV2M': [climate_data['QV2M']],
                        'TQV': [climate_data['TQV']],
                        'PS': [climate_data['PS']],
                    })

                    # Load the machine learning model based on the selected option
                    if model_option == "LightGBM":
                        model = load_model('models/lgbm_model')
                    elif model_option == "Random Forest":
                        model = load_model('models/rf_model')
                    elif model_option == "XGBoost":
                        model = load_model('models/xgb_model')

                    # Make predictions using the selected model
                    pred = model.predict(input_features)

                    # Map the prediction to text
                    pred_text = "⚠️ Berpotensi banjir" if pred == 1 else "✅ Tidak berpotensi banjir"

                    # Append prediction result to the list
                    prediction_results.append({
                        'Tanggal': tanggal.date(),
                        'Hasil Prediksi': pred_text
                    })

                    # Update progress bar
                    progress_bar.progress(20 + (80 * (single_date - selected_start_date).days) // (selected_end_date - selected_start_date).days)

                waiting_message3.empty()

                # Update progress bar and message
                progress_bar.progress(100)
                st.success("Prediksi rentang tanggal selesai!")

                # Display the prediction results as a DataFrame
                prediction_df = pd.DataFrame(prediction_results)
                st.subheader("Hasil Prediksi Rentang Tanggal")
                st.dataframe(prediction_df, use_container_width=True, hide_index=True)
                st.write("Sumber data: NASA Prediction Of Worldwide Energy Resources")
                
                # Show refresh button for the page
                if st.button("Reset"):
                    # Refresh the page
                    st.experimental_rerun()

# Halaman tentang
def show_tutorial_page():
    st.image("images/logo.png", width=350)
    st.title("📄 Tutorial")
    st.markdown("""

        ## Daftar Isi

        - [Dashboard](#dashboard)
            - [Data Cuaca](#data-cuaca)
            - [Peta Kejadian Banjir di Indonesia](#peta-kejadian-banjir-di-indonesia)
            - [Grafik Kejadian Banjir](#grafik-kejadian-banjir)
        - [Prediksi Banjir](#prediksi-banjir)
            - [Input Lokasi](#input-lokasi)
            - [Pilih Algoritma Model](#pilih-algoritma-model)
            - [Pilih Jenis Input Tanggal](#pilih-jenis-input-tanggal)
            - [Proses Prediksi](#proses-prediksi)    
    
        ## Dashboard
        
        Dashboard Pelampung.AI adalah halaman utama dari aplikasi yang menyediakan berbagai informasi terkait data cuaca dan kejadian banjir di Indonesia. Dashboard ini dirancang untuk memberikan pengguna akses yang mudah dan intuitif terhadap data cuaca terkini, peta kejadian banjir, serta grafik analisis kejadian banjir.

        ### Data Cuaca

        Pada halaman dashboard, Anda dapat melihat data cuaca terkini. Langkah-langkah berikut akan memandu Anda untuk melihat data cuaca:

        1. **Pilih kabupaten/kota**: Pada sidebar, Anda akan melihat daftar kabupaten/kota yang tersedia. Pilihlah kabupaten/kota yang ingin Anda lihat data cuacanya.

        2. **Tab Hari Ini**: Setelah memilih kabupaten/kota, Anda akan melihat tab "Hari Ini". Di tab ini, Anda dapat melihat informasi cuaca hari ini, seperti suhu, kelembapan, cuaca, arah angin, dan kecepatan angin. Informasi cuaca ditampilkan dalam bentuk *metric card* yang memberikan informasi seputar nilai cuaca beserta satuan yang sesuai. Pastikan untuk memeriksa sumber data cuaca yang berasal dari Badan Meteorologi, Klimatologi, dan Geofisika (BMKG).

        3. **Tab Besok**: Anda juga dapat melihat data cuaca untuk besok dengan memilih tab "Besok". Informasi yang ditampilkan pada tab ini sama dengan tab "Hari Ini", hanya berbeda pada nilai cuaca yang sesuai dengan hari besok.

        Berikut adalah data cuaca yang ditampilkan dalam Tab:

        - **Suhu (°C)**

        Informasi suhu memberikan gambaran tentang suhu udara pada saat ini. Suhu udara yang tinggi atau rendah dapat mempengaruhi kondisi cuaca secara keseluruhan dan dapat menjadi faktor penting dalam prediksi banjir. Data suhu membantu pengguna dalam memahami kondisi cuaca dan mempersiapkan langkah-langkah yang diperlukan.

        - **Suhu Maksimum dan Minimum (°C)**
        
        Informasi suhu maksimum dan minimum memberikan batasan atas dan bawah dari rentang suhu yang terjadi pada hari itu. Hal ini dapat memberikan gambaran tentang fluktuasi suhu dalam satu hari dan membantu pengguna dalam memperkirakan perubahan cuaca yang mungkin terjadi.

        - **Kelembapan (%)**
        
        Kelembapan udara mengacu pada kadar air dalam udara. Informasi kelembapan membantu pengguna dalam memahami tingkat kelembaban udara pada saat ini. Tingkat kelembapan yang tinggi dapat berkontribusi pada kondisi yang lebih lembap dan berpotensi mempengaruhi perkiraan banjir.

        - **Kelembapan Maksimum dan Minimum (%)**
        
        Informasi kelembapan maksimum dan minimum memberikan batasan atas dan bawah dari rentang kelembapan udara pada hari itu. Hal ini dapat memberikan gambaran tentang fluktuasi kelembapan dalam satu hari dan membantu pengguna dalam memperkirakan perubahan cuaca yang mungkin terjadi.

        - **Cuaca**
        
        Informasi cuaca memberikan gambaran tentang kondisi cuaca saat ini, seperti cerah, berawan, hujan, dan sebagainya. Cuaca yang tidak stabil atau cuaca hujan yang intens dapat berhubungan dengan risiko banjir yang lebih tinggi.

        - **Arah Angin (°)**
        
        Informasi arah angin mengindikasikan arah dari mana angin bertiup. Arah angin dapat mempengaruhi aliran air dan distribusi hujan dalam suatu wilayah. Informasi ini dapat membantu pengguna dalam memahami pola angin dan dampaknya terhadap kondisi banjir.

        - **Kecepatan Angin (m/s)**
        
        Informasi kecepatan angin mengindikasikan kecepatan dari angin yang berhembus. Kecepatan angin yang tinggi dapat mempengaruhi pergerakan awan, distribusi curah hujan, dan potensi banjir. Data ini membantu pengguna dalam memahami kondisi angin dan memprediksi kemungkinan banjir.
        
        ### Peta Kejadian Banjir di Indonesia

        Selain data cuaca, aplikasi Pelampung.AI juga menyediakan peta kejadian banjir di Indonesia. Berikut adalah langkah-langkah untuk melihat peta kejadian banjir:

        1. **Pilih Tahun**: Pada halaman dashboard, Anda akan menemukan *slider* untuk memilih tahun. Geser *slider* tersebut untuk memilih tahun yang Anda inginkan.

        2. **Peta Kejadian Banjir**: Setelah memilih tahun, Anda akan melihat peta yang menampilkan lokasi dan informasi kejadian banjir di Indonesia. Setiap lokasi pada peta memiliki *popup* yang berisi detail informasi terkait kejadian banjir, seperti tanggal, jumlah korban, kerusakan, dan sebagainya. Pastikan untuk memeriksa sumber data yang berasal dari Badan Nasional Penanggulangan Bencana (BNPB).

        ### Grafik Kejadian Banjir

        Selain peta, aplikasi Pelampung.AI juga menyajikan grafik terkait kejadian banjir. Berikut adalah langkah-langkah untuk melihat grafik kejadian banjir:

        1. **Kejadian Banjir per Provinsi**: Anda akan menemukan grafik batang yang menunjukkan jumlah kejadian banjir pada tahun yang Anda pilih. Grafik ini mengurutkan provinsi-provinsi berdasarkan jumlah kejadian banjir secara menurun. Pastikan untuk memeriksa sumber data yang berasal dari BNPB.

        2. **Grafik Kejadian Banjir di Indonesia**: Anda akan menemukan grafik garis yang menunjukkan tren kejadian banjir di Indonesia dari tahun 2003 hingga tahun 2023. Grafik ini menggambarkan jumlah kejadian banjir secara tahunan. Pastikan untuk memeriksa sumber data yang berasal dari BNPB.

        > Semua informasi yang ditampilkan pada Dashboard Pelampung.ai didukung oleh sumber data resmi seperti NASA Prediction Of Worldwide Energy Resources, Badan Meteorologi, Klimatologi, dan Geofisika (BMKG) untuk data cuaca, serta Badan Nasional Penanggulangan Bencana (BNPB) untuk data kejadian banjir.
        
        Dengan menggunakan Dashboard Pelampung.ai, pengguna dapat memantau kondisi cuaca terkini dan mengakses informasi tentang kejadian banjir di Indonesia untuk tujuan analisis dan pengambilan keputusan yang lebih baik.

        ---
        
        ## Prediksi Banjir
        
        ### Input Lokasi
        Pertama-tama, Anda akan diminta untuk memilih opsi input lokasi, yaitu **"Alamat"** atau **"Koordinat"**.

        Jika Anda memilih **"Alamat"**,
        1. Anda dapat memilih provinsi, kabupaten/kota, kecamatan, dan desa dari daftar yang tersedia.
        2. Setelah memilih lokasi, aplikasi akan menggabungkan lokasi yang dipilih menjadi satu string dan melakukan geocode untuk mendapatkan koordinat latitude dan longitude.
        3. Latitude dan longitude tersebut akan ditampilkan dan juga ditampilkan peta dengan lokasi yang telah dipilih.

        > Jika alamat tidak ditemukan atau lokasi tidak valid, Anda akan mendapatkan pesan kesalahan dan diminta untuk memilih lokasi yang lain.

        Jika Anda memilih "Koordinat",
        1. Anda perlu memasukkan latitude dan longitude secara manual.
        > Anda dapat menggunakan layanan [Google Maps](http://maps.google.com/) untuk membantu menemukan latitude dan longitude yang tepat.
        2. Setelah memasukkan latitude dan longitude, aplikasi akan melakukan reverse geocode untuk mendapatkan alamat berdasarkan koordinat yang Anda masukkan. Alamat tersebut akan ditampilkan.

        ### Pilih Algoritma Model
        Setelah memilih lokasi, Anda akan diminta untuk memilih algoritma model yang akan digunakan untuk prediksi. Tiga opsi algoritma yang tersedia adalah:

        - **LightGBM:** Algoritma ini memiliki performa yang baik dalam memodelkan variabel lokasi seperti lintang dan bujur, sehingga cocok untuk analisis yang fokus pada faktor spasial. LightGBM menggunakan pendekatan Gradient Boosting dan keuntungan dari pembelajaran berbasis pohon untuk menghasilkan prediksi yang akurat. Jika variabel lokasi menjadi faktor penting dalam prediksi banjir, LightGBM merupakan pilihan yang tepat.

        - **Random Forest:** Algoritma ini dapat memberikan hasil yang baik dalam memodelkan variabel curah hujan seperti curah hujan dan kualitas uap air. Dengan pendekatan ensemble learning, Random Forest menggabungkan prediksi dari beberapa pohon keputusan untuk menghasilkan hasil akhir. Keunggulan Random Forest terletak pada kemampuannya dalam menangani variabel numerik dan kategorikal, serta mampu mengatasi masalah overfitting. Jika variabel curah hujan menjadi faktor penting dalam prediksi banjir, Random Forest merupakan pilihan yang tepat.

        - **XGBoost:** Algoritma ini menggunakan pendekatan Gradient Boosting dan dikenal karena performanya yang tinggi dalam mengatasi masalah regresi dan klasifikasi. XGBoost dapat bekerja dengan baik dalam memodelkan variabel tanggal seperti hari, sehingga cocok digunakan dalam analisis yang melibatkan tren temporal. Selain itu, XGBoost memiliki kemampuan untuk menangani data dengan ukuran besar, fitur-fitur yang tidak terstruktur, dan fitur pengoptimalan yang kuat. Jika variabel tanggal menjadi faktor penting dalam prediksi banjir, XGBoost merupakan pilihan yang optimal.
        
        Anda dapat memilih salah satu dari opsi tersebut sebagai model prediksi. Dengan mempertimbangkan preferensi dan keunggulan masing-masing algoritma, pemilihan algoritma yang tepat dapat memberikan hasil yang optimal dalam pemodelan fitur-fitur tersebut.

        > Penting untuk diingat bahwa pemilihan algoritma tergantung pada data yang Anda miliki dan karakteristiknya. Evaluasi dan eksperimen dengan beberapa algoritma tersebut dapat membantu Anda menentukan model terbaik untuk prediksi banjir.

        ### Pilih Jenis Input Tanggal
        Selanjutnya, Anda akan diminta untuk memilih jenis input tanggal, yaitu **"Tanggal Satuan"** atau **"Rentang Tanggal"**.

        Jika Anda memilih **"Tanggal Satuan"**,
        1. Anda perlu memilih tanggal secara individu dengan menggunakan kalender.
        2. Setelah memilih tanggal, Anda dapat menekan tombol "🔍Prediksi" untuk memulai proses prediksi.

        Jika Anda memilih **"Rentang Tanggal"**, 
        1. Anda perlu memilih tanggal awal dan tanggal akhir dengan menggunakan rentang tanggal.
        2. Setelah memilih rentang tanggal, Anda dapat menekan tombol "🔍Prediksi" untuk memulai proses prediksi.

        ### Proses Prediksi
        Setelah memilih algoritma model dan jenis input tanggal, Anda akan memulai proses prediksi. Proses prediksi akan melibatkan pengambilan data iklim dari NASA Prediction Of Worldwide Energy Resources, pengolahan data, dan penggunaan model machine learning yang telah dipilih.

        Proses prediksi akan mengambil data iklim berdasarkan lokasi dan tanggal yang Anda pilih. Data iklim tersebut akan digunakan sebagai fitur input dalam model machine learning. Setelah mendapatkan hasil prediksi, aplikasi akan menampilkan hasil prediksi berupa teks yang menggambarkan potensi banjir. Output teks berupa:
        - ⚠️ Berpotensi banjir
        - ✅ Tidak berpotensi banjir

        Kode yang diberikan akan memulai proses prediksi sesuai dengan pilihan lokasi, model, dan tanggal yang Anda inputkan. Kemudian, hasil prediksi dan data iklim akan ditampilkan dengan menggunakan beberapa metrik yang relevan.

        Jika Anda ingin melakukan prediksi ulang, Anda dapat menekan tombol **"Reset"** untuk memulai kembali.
        
        ---""")

# Main function
def main():
    st.sidebar.image("images/logo.png", use_column_width=True)
    page = st.sidebar.radio("Pilih Halaman", ["📊 Dashboard", "🔍 Prediksi Banjir", "📄 Tutorial"])
    
    if page == "📊 Dashboard":
        show_dashboard()
    elif page == "🔍 Prediksi Banjir":
        show_prediction_page()
    elif page == "📄 Tutorial":
        show_tutorial_page()

    st.sidebar.markdown(
        '''
        ## Credits
        **Dosen Pembimbing:**

        Sachnaz Desta Oktarina, S.Stat., M.Agr., Ph.D.
        
        **Anggota Kelompok:**
        - Muhammad Dzakwan Alifi
        - Indra Mahib Zuhair Riyanto
        - Zaima Firoos Likan
        '''
    )
    
if __name__ == "__main__":
    main()