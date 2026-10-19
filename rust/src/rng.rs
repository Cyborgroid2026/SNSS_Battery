//! SplitMix64 — spec §1. Python·C# 와 같은 수열.

pub struct SplitMix64 {
    state: u64,
}

impl SplitMix64 {
    pub fn new(seed: u64) -> Self {
        Self { state: seed }
    }

    pub fn next_u64(&mut self) -> u64 {
        self.state = self.state.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.state;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }

    /// [0, 1), 53비트
    pub fn u(&mut self) -> f64 {
        (self.next_u64() >> 11) as f64 * (1.0 / (1u64 << 53) as f64)
    }

    pub fn uniform(&mut self, a: f64, b: f64) -> f64 {
        a + (b - a) * self.u()
    }

    /// Knuth (spec §1)
    pub fn poisson(&mut self, lam: f64) -> u32 {
        let limit = (-lam).exp();
        let (mut k, mut p) = (0u32, 1.0f64);
        loop {
            p *= self.u();
            if p <= limit {
                return k;
            }
            k += 1;
        }
    }
}

pub fn round_half_up(v: f64) -> i64 {
    (v + 0.5).floor() as i64
}
