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
};

#[derive(Clone, Debug, Default)]
pub(crate) struct CountryDatabase {
    ipv4: HashMap<(u32, u8), [u8; 2]>,
    ipv6: HashMap<(u128, u8), [u8; 2]>,
}

impl CountryDatabase {
    pub(crate) fn country(&self, ip: IpAddr) -> Option<[u8; 2]> {
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
}

pub(crate) fn configured() -> bool {
    env::var("RUSTDESK_GEOIP_CSV_DIR")
        .map(|dir| !dir.trim().is_empty())
        .unwrap_or(false)
}

pub(crate) fn load_from_environment() -> Result<Option<CountryDatabase>, String> {
    let dir = match env::var("RUSTDESK_GEOIP_CSV_DIR") {
        Ok(value) if !value.trim().is_empty() => value,
        _ => return Ok(None),
    };
    load(Path::new(&dir)).map(Some)
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
    fn rejects_missing_files_and_broken_csv() {
        let dir = tempfile::tempdir().unwrap();
        assert!(load(dir.path()).is_err());
        assert!(csv_fields("a,\"b,c\",d").is_ok());
        assert!(csv_fields("a,\"unfinished").is_err());
    }
}
