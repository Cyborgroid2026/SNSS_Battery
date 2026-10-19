//! 아주 작은 JSON 파서·작성기 (외부 크레이트 없이).

use std::collections::BTreeMap;

#[derive(Debug, Clone)]
pub enum Json {
    Null,
    Bool(bool),
    Num(f64),
    Str(String),
    Arr(Vec<Json>),
    Obj(BTreeMap<String, Json>),
}

impl Json {
    pub fn get(&self, k: &str) -> Option<&Json> {
        if let Json::Obj(m) = self { m.get(k) } else { None }
    }
    pub fn num(&self, k: &str) -> f64 {
        match self.get(k) {
            Some(Json::Num(v)) => *v,
            _ => panic!("숫자 필드 없음: {k}"),
        }
    }
    pub fn str(&self, k: &str) -> String {
        match self.get(k) {
            Some(Json::Str(s)) => s.clone(),
            _ => panic!("문자열 필드 없음: {k}"),
        }
    }
    pub fn flag(&self, k: &str) -> bool {
        matches!(self.get(k), Some(Json::Bool(true)))
    }
}

pub fn parse(src: &str) -> Json {
    let b: Vec<char> = src.chars().collect();
    let mut i = 0;
    let v = value(&b, &mut i);
    v
}

fn ws(b: &[char], i: &mut usize) {
    while *i < b.len() && b[*i].is_whitespace() {
        *i += 1;
    }
}

fn value(b: &[char], i: &mut usize) -> Json {
    ws(b, i);
    match b[*i] {
        '{' => {
            *i += 1;
            let mut m = BTreeMap::new();
            loop {
                ws(b, i);
                if b[*i] == '}' {
                    *i += 1;
                    break;
                }
                let k = match value(b, i) {
                    Json::Str(s) => s,
                    _ => panic!("키는 문자열"),
                };
                ws(b, i);
                *i += 1; // ':'
                let v = value(b, i);
                m.insert(k, v);
                ws(b, i);
                if b[*i] == ',' {
                    *i += 1;
                }
            }
            Json::Obj(m)
        }
        '[' => {
            *i += 1;
            let mut a = Vec::new();
            loop {
                ws(b, i);
                if b[*i] == ']' {
                    *i += 1;
                    break;
                }
                a.push(value(b, i));
                ws(b, i);
                if b[*i] == ',' {
                    *i += 1;
                }
            }
            Json::Arr(a)
        }
        '"' => {
            *i += 1;
            let mut s = String::new();
            while b[*i] != '"' {
                if b[*i] == '\\' {
                    *i += 1;
                    match b[*i] {
                        'n' => s.push('\n'),
                        't' => s.push('\t'),
                        'u' => {
                            let hex: String = b[*i + 1..*i + 5].iter().collect();
                            s.push(char::from_u32(u32::from_str_radix(&hex, 16).unwrap()).unwrap_or('?'));
                            *i += 4;
                        }
                        c => s.push(c),
                    }
                } else {
                    s.push(b[*i]);
                }
                *i += 1;
            }
            *i += 1;
            Json::Str(s)
        }
        't' => {
            *i += 4;
            Json::Bool(true)
        }
        'f' => {
            *i += 5;
            Json::Bool(false)
        }
        'n' => {
            *i += 4;
            Json::Null
        }
        _ => {
            let st = *i;
            while *i < b.len() && "+-0123456789.eE".contains(b[*i]) {
                *i += 1;
            }
            Json::Num(b[st..*i].iter().collect::<String>().parse().unwrap())
        }
    }
}

pub fn esc(s: &str) -> String {
    let mut o = String::from("\"");
    for c in s.chars() {
        match c {
            '"' => o.push_str("\\\""),
            '\\' => o.push_str("\\\\"),
            '\n' => o.push_str("\\n"),
            _ => o.push(c),
        }
    }
    o.push('"');
    o
}

pub fn num(v: f64) -> String {
    if v.is_finite() { format!("{:e}", v) } else { "null".into() }
}
