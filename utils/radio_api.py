import aiohttp


async def search_radio_stations(query: str, limit: int = 10):
    url = "https://de1.api.radio-browser.info/json/stations/search"
    params = {
        "name": query,
        "limit": limit,
        "hidebroken": "true",
        "order": "clickcount",
        "reverse": "true"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=10) as resp:
                if resp.status != 200:
                    return []
                return await resp.json()
    except Exception as e:
        print(f"Ошибка Radio API: {e}")
        return []