//! Country-level IP lookup using the official MaxMind GeoLite2 Country CSV export.
//! Files are supplied by administrators under their own MaxMind license.
use ipnetwork::IpNetwork;
use std::{
    collections::HashMap,
    env,
    fs::File,
    io::{BufRead, BufReader},
    net::IpAddr,
    path::Path,
    str::FromStr,
    sync::Arc,
};

#[derive(Clone, Default)]
pub(crate) struct CountryDatabase {
    ipv4: HashMap<(u32, u8), [u8; 2]>,
    ipv6: HashMap<(u128, u8), [u8; 2]>,
    mmdb: Option<Arc<maxminddb::Reader<Vec<u8>>>>,
}

impl std::fmt::Debug for CountryDatabase {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("CountryDatabase")
            .field("csv_networks", &(self.ipv4.len() + self.ipv6.len()))
            .field("mmdb", &self.mmdb.is_some())
            .finish()
    }
}

impl CountryDatabase {
    pub(crate) fn country(&self, ip: IpAddr) -> Option<[u8; 2]> {
        if let Some(reader) = &self.mmdb {
            if let Ok(record) = reader.lookup::<maxminddb::geoip2::Country>(ip) {
                let code = record
                    .country
                    .and_then(|country| country.iso_code)
                    .or_else(|| record.registered_country.and_then(|country| country.iso_code));
                if let Some(code) = code.and_then(two_letter_code) {
                    return Some(code);
                }
            }
        }
        match ip {
            IpAddr::V4(ip) => {
                let numeric = u32::from(ip);
                for prefix in (0..=32).rev() {
                    let network = if prefix == 0 {
                        0
                    } else {
                        numeric & (u32::MAX << (32 - prefix))
                    };
                    if let Some(country) = self.ipv4.get(&(network, prefix as u8)) {
                        return Some(*country);
                    }
                }
            }
            IpAddr::V6(ip) => {
                let numeric = u128::from(ip);
                for prefix in (0..=128).rev() {
                    let network = if prefix == 0 {
                        0
                    } else {
                        numeric & (u128::MAX << (128 - prefix))
                    };
                    if let Some(country) = self.ipv6.get(&(network, prefix as u8)) {
                        return Some(*country);
                    }
                }
            }
        };
        None
    }

    pub(crate) fn block_count(&self) -> usize {
        self.ipv4.len() + self.ipv6.len()
    }

    pub(crate) fn data_format(&self) -> &'static str {
        match (self.mmdb.is_some(), self.block_count() > 0) {
            (true, true) => "MMDB and CSV",
            (true, false) => "MMDB",
            (false, _) => "CSV",
        }
    }
}

fn two_letter_code(value: &str) -> Option<[u8; 2]> {
    let bytes = value.as_bytes();
    if bytes.len() != 2 || !bytes.iter().all(u8::is_ascii_uppercase) {
        return None;
    }
    Some([bytes[0], bytes[1]])
}

pub(crate) fn configured() -> bool {
    ["RUSTDESK_GEOIP_MMDB_FILE", "RUSTDESK_GEOIP_CSV_DIR"]
        .iter()
        .any(|name| env::var(name).map(|value| !value.trim().is_empty()).unwrap_or(false))
}

pub(crate) fn load_from_environment() -> Result<Option<CountryDatabase>, String> {
    let mmdb = env::var("RUSTDESK_GEOIP_MMDB_FILE")
        .ok().filter(|value| !value.trim().is_empty());
    let csv = env::var("RUSTDESK_GEOIP_CSV_DIR")
        .ok().filter(|value| !value.trim().is_empty());
    if mmdb.is_none() && csv.is_none() {
        return Ok(None);
    }
    let mut data = match csv {
        Some(directory) => load(Path::new(&directory))?,
        None => CountryDatabase::default(),
    };
    if let Some(file) = mmdb {
        let reader = maxminddb::Reader::open_readfile(Path::new(&file))
            .map_err(|error| format!("{file}: {error}"))?;
        data.mmdb = Some(Arc::new(reader));
    }
    Ok(Some(data))
}

// The country-name columns of MaxMind's CSV can contain commas or quotes.
// Parse the CSV grammar instead of splitting each location row on commas.
fn csv_fields(line: &str) -> Result<Vec<String>, String> {
    let mut parts = Vec::new();
    let mut field = String::new();
    let mut chars = line.trim_end_matches(['\r', '\n']).chars().peekable();
    let mut quoted = false;
    while let Some(ch) = chars.next() {
        match ch {
            '"' if quoted && chars.peek() == Some(&'"') => {
                chars.next();
                field.push('"');
            }
            '"' => quoted = !quoted,
            ',' if !quoted => {
                parts.push(std::mem::take(&mut field));
            }
            _ => field.push(ch),
        }
    }
    if quoted {
        return Err("CSV line has an unmatched quotation mark".to_owned());
    }
    parts.push(field);
    Ok(parts)
}

fn column(columns: &[String], name: &str) -> Result<usize, String> {
    columns
        .iter()
        .position(|value| value == name)
        .ok_or_else(|| format!("GeoLite2 CSV has no {name} column"))
}

fn open_rows(
    path: &Path,
    mut visit: impl FnMut(&[String], &[String]) -> Result<(), String>,
) -> Result<(), String> {
    let file = File::open(path).map_err(|e| format!("{}: {e}", path.display()))?;
    let mut rows = BufReader::new(file).lines();
    let first = rows
        .next()
        .ok_or_else(|| format!("{} is empty", path.display()))?
        .map_err(|e| e.to_string())?;
    let mut headers = csv_fields(&first)?;
    if let Some(value) = headers.first_mut() {
        *value = value.trim_start_matches('\u{feff}').to_owned();
    }
    for (index, line) in rows.enumerate() {
        let line = line.map_err(|e| e.to_string())?;
        if line.len() > 8192 {
            return Err(format!("{}: line {} is too long", path.display(), index + 2));
        }
        let fields = csv_fields(&line)?;
        if fields.len() != headers.len() {
            return Err(format!("{}: line {} has the wrong number of columns", path.display(), index + 2));
        }
        visit(&headers, &fields)?;
    }
    Ok(())
}

fn read_countries(path: &Path) -> Result<HashMap<String, [u8; 2]>, String> {
    let mut countries = HashMap::new();
    open_rows(path, |headers, row| {
        let id = &row[column(headers, "geoname_id")?];
        let iso = row[column(headers, "country_iso_code")?].trim().to_ascii_uppercase();
        let chars = iso.as_bytes();
        if chars.len() == 2 && chars.iter().all(|c| c.is_ascii_uppercase()) {
            countries.insert(id.clone(), [chars[0], chars[1]]);
        }
        Ok(())
    })?;
    Ok(countries)
}

fn read_blocks(
    path: &Path,
    countries: &HashMap<String, [u8; 2]>,
    db: &mut CountryDatabase,
) -> Result<(), String> {
    open_rows(path, |headers, row| {
        let network = &row[column(headers, "network")?];
        let geoname = &row[column(headers, "geoname_id")?];
        let registered = &row[column(headers, "registered_country_geoname_id")?];
        let country = countries.get(geoname).or_else(|| countries.get(registered));
        if let Some(country) = country {
            match IpNetwork::from_str(network).map_err(|e| e.to_string())? {
                IpNetwork::V4(network) => {
                    db.ipv4.insert((u32::from(network.network()), network.prefix()), *country);
                }
                IpNetwork::V6(network) => {
                    db.ipv6.insert((u128::from(network.network()), network.prefix()), *country);
                }
            }
        } else {
            // Unknown locations are intentionally omitted. The relay selector
            // will use CIDR preferences or the existing round-robin behavior.
            IpNetwork::from_str(network).map_err(|e| e.to_string())?;
        }
        Ok(())
    })
}

pub(crate) fn load(dir: &Path) -> Result<CountryDatabase, String> {
    let locations = dir.join("GeoLite2-Country-Locations-en.csv");
    let blocks_v4 = dir.join("GeoLite2-Country-Blocks-IPv4.csv");
    let blocks_v6 = dir.join("GeoLite2-Country-Blocks-IPv6.csv");
    let countries = read_countries(&locations)?;
    if countries.is_empty() {
        return Err("GeoLite2 Country CSV has no ISO country codes".to_owned());
    }
    let mut result = CountryDatabase::default();
    read_blocks(&blocks_v4, &countries, &mut result)?;
    read_blocks(&blocks_v6, &countries, &mut result)?;
    if result.block_count() == 0 {
        return Err("GeoLite2 Country CSV has no usable IP networks".to_owned());
    }
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{fs, net::IpAddr};

    #[test]
    fn loads_maxmind_country_csv_for_ipv4_and_ipv6() {
        let dir = tempfile::tempdir().unwrap();
        fs::write(
            dir.path().join("GeoLite2-Country-Locations-en.csv"),
            "geoname_id,locale_code,continent_code,continent_name,country_iso_code,country_name\n\
            1861060,en,AS,Asia,JP,Japan\n\
            6252001,en,NA,North America,US,\"United States of America\"\n\
            9999,en,AS,Asia,,Asia\n",
        ).unwrap();
        fs::write(
            dir.path().join("GeoLite2-Country-Blocks-IPv4.csv"),
            "network,geoname_id,registered_country_geoname_id\n\
            203.0.113.0/24,1861060,\n\
            203.0.113.128/25,6252001,\n\
            198.51.100.0/24,,6252001\n\
            192.0.2.0/24,9999,\n",
        ).unwrap();
        fs::write(
            dir.path().join("GeoLite2-Country-Blocks-IPv6.csv"),
            "network,geoname_id,registered_country_geoname_id\n\
            2001:db8:1::/48,1861060,\n",
        ).unwrap();
        let geo = load(dir.path()).unwrap();
        assert_eq!(geo.block_count(), 4);
        assert_eq!(geo.country("203.0.113.1".parse::<IpAddr>().unwrap()), Some(*b"JP"));
        assert_eq!(geo.country("203.0.113.200".parse::<IpAddr>().unwrap()), Some(*b"US"));
        assert_eq!(geo.country("198.51.100.1".parse::<IpAddr>().unwrap()), Some(*b"US"));
        assert_eq!(geo.country("2001:db8:1::1".parse::<IpAddr>().unwrap()), Some(*b"JP"));
        assert_eq!(geo.country("192.0.2.1".parse::<IpAddr>().unwrap()), None);
    }

    #[test]
    fn reads_maxmind_sample_mmdb_for_ipv4_and_ipv6() {
        let bytes = include_bytes!("../tests/fixtures/GeoLite2-Country-Test.mmdb");
        let reader = maxminddb::Reader::from_source(bytes.to_vec()).unwrap();
        let db = CountryDatabase {
            mmdb: Some(Arc::new(reader)),
            ..CountryDatabase::default()
        };
        assert_eq!(db.data_format(), "MMDB");
        assert_eq!(db.country("2.125.160.216".parse().unwrap()), Some(*b"GB"));
        assert_eq!(db.country("50.114.1.2".parse().unwrap()), Some(*b"US"));
        assert_eq!(db.country("2001:218::1".parse().unwrap()), Some(*b"JP"));
        assert_eq!(db.country("2001:220::1".parse().unwrap()), Some(*b"KR"));

        // CSV remains available for IP ranges absent from the MMDB source.
        let mut combined = db.clone();
        let mut csv = CountryDatabase::default();
        let jp_v4 = ("203.0.113.0".parse::<std::net::Ipv4Addr>().unwrap(), 24u8);
        csv.ipv4.insert((u32::from(jp_v4.0), jp_v4.1), *b"JP");
        combined.ipv4 = csv.ipv4.clone();
        assert_eq!(combined.data_format(), "MMDB and CSV");
        assert_eq!(combined.country("203.0.113.123".parse().unwrap()), Some(*b"JP"));
        assert_eq!(combined.country("2001:218::1".parse().unwrap()), db.country("2001:218::1".parse().unwrap()));
    }

    #[test]
    fn mmdb_file_validation_and_country_code_conversion() {
        assert_eq!(two_letter_code("JP"), Some(*b"JP"));
        assert_eq!(two_letter_code("us"), None);
        assert_eq!(two_letter_code("JPN"), None);
        let dir = tempfile::tempdir().unwrap();
        let file = dir.path().join("not-a-country-database.mmdb");
        fs::write(&file, b"invalid mmdb").unwrap();
        assert!(maxminddb::Reader::open_readfile(&file).is_err());

        let csv = CountryDatabase::default();
        assert_eq!(csv.data_format(), "CSV");
        let mmdb = load_from_environment_file(&file);
        assert!(mmdb.is_err());
    }

    fn load_from_environment_file(file: &Path) -> Result<maxminddb::Reader<Vec<u8>>, String> {
        maxminddb::Reader::open_readfile(file).map_err(|error| error.to_string())
    }

    #[test]
    fn rejects_missing_files_and_broken_csv() {
        let dir = tempfile::tempdir().unwrap();
        assert!(load(dir.path()).is_err());
        assert!(csv_fields("a,\"b,c\",d").is_ok());
        assert!(csv_fields("a,\"unfinished").is_err());
    }
}
