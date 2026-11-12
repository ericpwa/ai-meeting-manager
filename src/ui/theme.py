"""企業視覺主題與玻璃擬態 UI 元件庫 (`src/ui/theme.py`).

設計基調（依據使用者共識）：
1. 企業色（藍白灰 — 取自 INPOWER 銓泰環能科技企業識別與制服波浪配色）：
   - 深海藏青波浪 (Deep Navy Wave)：`#162238` / `#1E293B`
   - 企業寶石鋼藍 (Corporate Cobalt Steel Blue)：`#1E4E79` / `#255C99` / `#2563EB`
   - 純淨珍珠白與冰川淺灰白 (Crisp White & Ice Gray)：`#FFFFFF` / `#F8FAFC` / `#F1F5F9`
   - 科技金屬銀灰 (Metallic Cool Gray)：`#94A3B8` / `#64748B`
2. 霓虹微光四色燈號 (Neon Glow 4-Color Traffic Lights)：
   - 🔴 紅燈 (Neon Crimson)：`#EF4444` (逾期未完成 / 執行受阻)
   - 🟡 黃燈 (Neon Amber)：`#F59E0B` (治理缺口 / 3日內即將到期)
   - 🔵 藍燈 (Neon Cobalt/Cyan)：`#3B82F6` (未完成 / 正常進行中)
   - 🟢 綠燈 (Neon Emerald)：`#10B981` (已完成 Done + 具 T 佐證)
3. 玻璃擬態卡片 (Glassmorphism) + 圓角立體色帶指標卡 + 膠囊分段式六大頁籤導覽列。
"""

from __future__ import annotations

import html
import streamlit as st

from src.schemas.models import ActionItem


def get_inpower_logo_svg(width: int = 236, height: int = 92, compact: bool = False) -> str:
    """產出『INPOWER 銓泰環能科技』高解析向量 SVG 企業 Logo（精準還原附圖胸口企業識別設計）."""
    uid = "inp_sb" if compact else "inp_hero"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 340 132" width="{width}" height="{height}" role="img" aria-label="INPOWER 銓泰環能科技">
  <defs>
    <linearGradient id="{uid}_bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#193759"/>
      <stop offset="52%" stop-color="#1E4E79"/>
      <stop offset="100%" stop-color="#286094"/>
    </linearGradient>
    <linearGradient id="{uid}_metal" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#E2E8F0"/>
      <stop offset="48%" stop-color="#CBD5E1"/>
      <stop offset="100%" stop-color="#94A3B8"/>
    </linearGradient>
    <linearGradient id="{uid}_top_arc" x1="0%" y1="50%" x2="100%" y2="50%">
      <stop offset="0%" stop-color="#EF4444"/>
      <stop offset="35%" stop-color="#F97316"/>
      <stop offset="68%" stop-color="#FACC15"/>
      <stop offset="100%" stop-color="#4ADE80"/>
    </linearGradient>
    <linearGradient id="{uid}_bot_arc" x1="100%" y1="50%" x2="0%" y2="50%">
      <stop offset="0%" stop-color="#38BDF8"/>
      <stop offset="42%" stop-color="#6366F1"/>
      <stop offset="100%" stop-color="#F43F5E"/>
    </linearGradient>
    <radialGradient id="{uid}_orb_red" cx="70%" cy="28%" r="58%">
      <stop offset="0%" stop-color="#FF5A5F"/>
      <stop offset="55%" stop-color="#F97316" stop-opacity="0.78"/>
      <stop offset="100%" stop-color="#F97316" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="{uid}_orb_yel" cx="25%" cy="32%" r="58%">
      <stop offset="0%" stop-color="#FEF08A"/>
      <stop offset="58%" stop-color="#84CC16" stop-opacity="0.80"/>
      <stop offset="100%" stop-color="#22C55E" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="{uid}_orb_blu" cx="68%" cy="75%" r="60%">
      <stop offset="0%" stop-color="#38BDF8"/>
      <stop offset="55%" stop-color="#2563EB" stop-opacity="0.88"/>
      <stop offset="100%" stop-color="#1D4ED8" stop-opacity="0"/>
    </radialGradient>
    <filter id="{uid}_glow" x="-15%" y="-15%" width="130%" height="130%">
      <feDropShadow dx="0" dy="2" stdDeviation="2.2" flood-color="#0F172A" flood-opacity="0.45"/>
    </filter>
  </defs>
  <!-- 企業制服口袋盾型底襯 (重現純白領口波浪 + 深海藏青色帶 + 寶石鋼藍底色) -->
  <rect x="3" y="3" width="334" height="126" rx="18" fill="url(#{uid}_bg)" stroke="rgba(255,255,255,0.32)" stroke-width="1.5"/>
  <path d="M 3 22 Q 92 36 175 18 T 337 16 L 337 3 L 3 3 Z" fill="rgba(255,255,255,0.16)"/>
  <path d="M 3 30 Q 92 44 175 26 T 337 24 L 337 15 Q 250 10 175 20 T 3 20 Z" fill="rgba(22,34,56,0.55)"/>
  <!-- 上方順時針漸層流線箭頭 (紅 -> 橙 -> 黃 -> 綠，由薄漸厚收於箭頭) -->
  <path d="M 118 41 C 142 12, 198 10, 224 34 L 231 28 L 235 45 L 217 41 L 221 37 C 196 17, 145 19, 118 41 Z" fill="url(#{uid}_top_arc)" filter="url(#{uid}_glow)"/>
  <!-- 下方順時針漸層流線箭頭 (藍 -> 靛紫 -> 珊瑚紅，由薄漸厚收於箭頭) -->
  <path d="M 218 72 C 194 99, 138 101, 111 76 L 104 82 L 100 64 L 118 69 L 114 73 C 139 93, 191 91, 218 72 Z" fill="url(#{uid}_bot_arc)" filter="url(#{uid}_glow)"/>
  <!-- IN 字樣 (大號銀灰金屬粗體) -->
  <text x="26" y="72" font-family="'Inter', 'Segoe UI', 'Helvetica Neue', Arial, sans-serif" font-size="45" font-weight="900" letter-spacing="1" fill="url(#{uid}_metal)" filter="url(#{uid}_glow)">IN</text>
  <!-- P 字樣 -->
  <text x="110" y="70" font-family="'Inter', 'Segoe UI', 'Helvetica Neue', Arial, sans-serif" font-size="33" font-weight="800" fill="url(#{uid}_metal)" filter="url(#{uid}_glow)">P</text>
  <!-- O 四色能量球體 (紅/黃/綠/藍 + 白色高光外環) -->
  <g filter="url(#{uid}_glow)">
    <circle cx="165" cy="56" r="18.5" fill="#22C55E"/>
    <circle cx="165" cy="56" r="18.5" fill="url(#{uid}_orb_yel)"/>
    <circle cx="165" cy="56" r="18.5" fill="url(#{uid}_orb_red)"/>
    <circle cx="165" cy="56" r="18.5" fill="url(#{uid}_orb_blu)"/>
    <circle cx="165" cy="56" r="18.5" fill="none" stroke="#FFFFFF" stroke-width="1.8" stroke-opacity="0.92"/>
  </g>
  <!-- WER 字樣 -->
  <text x="190" y="70" font-family="'Inter', 'Segoe UI', 'Helvetica Neue', Arial, sans-serif" font-size="33" font-weight="800" letter-spacing="1.2" fill="url(#{uid}_metal)" filter="url(#{uid}_glow)">WER</text>
  <!-- 銓泰環能科技 白色標準字 -->
  <text x="170" y="116" text-anchor="middle" font-family="'PingFang TC', 'Microsoft JhengHei', 'Noto Sans TC', sans-serif" font-size="20.5" font-weight="700" letter-spacing="5.5" fill="#FFFFFF" filter="url(#{uid}_glow)">銓泰環能科技</text>
</svg>"""


def inject_corporate_theme() -> None:
    """注入『INPOWER 銓泰環能科技』藍白灰企業色 ＋ 霓虹微光四色燈號 ＋ 玻璃擬態全局 CSS."""
    st.markdown(
        """
        <style>
        /* ==========================================================================
           1. 全域字體與企業藍白灰背景基調 (Corporate Blue-White-Gray Palette)
           ========================================================================== */
        :root {
            --inp-navy: #162238;
            --inp-cobalt: #1E4E79;
            --inp-blue: #2563EB;
            --inp-sky: #38BDF8;
            --inp-silver: #94A3B8;
            --inp-slate: #475569;
            --inp-ice-bg: #F1F5F9;
            --inp-glass-bg: rgba(255, 255, 255, 0.86);
            --inp-glass-border: rgba(30, 78, 121, 0.16);
            --neon-red: #EF4444;
            --neon-amber: #F59E0B;
            --neon-blue: #3B82F6;
            --neon-green: #10B981;
        }

        .stApp {
            background:
                radial-gradient(1200px 500px at 8% -5%, rgba(37, 99, 235, 0.09), transparent 60%),
                radial-gradient(1000px 480px at 95% 0%, rgba(30, 78, 121, 0.10), transparent 55%),
                linear-gradient(180deg, #F8FAFC 0%, #EEF2F7 52%, #F8FAFC 100%);
            color: #0F172A;
        }

        .block-container {
            padding-top: 1.5rem !important;
            padding-bottom: 3rem !important;
            max-width: 1440px !important;
        }

        /* 隱藏原生頂部重複 h1，交由企業 Hero Banner 呈現主視覺（保留 DOM 供 AppTest E2E 驗證） */
        h1 {
            font-size: 0 !important;
            line-height: 0 !important;
            height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
            overflow: hidden !important;
        }
        h2, h3, h4 {
            color: #162238 !important;
            font-weight: 700 !important;
        }

        /* ==========================================================================
           2. 頂部漸層商務橫幅 (Hero Header Banner + 企業制服藍白深藍波浪漸層 + 玻璃擬態膠囊)
           ========================================================================== */
        .inpower-hero-card {
            position: relative;
            overflow: hidden;
            border-radius: 20px;
            padding: 22px 28px;
            margin-bottom: 18px;
            background: linear-gradient(132deg, #162238 0%, #1B3B64 42%, #1E4E79 76%, #255C99 100%);
            box-shadow:
                0 16px 36px -10px rgba(22, 34, 56, 0.35),
                0 4px 12px -2px rgba(30, 78, 121, 0.22),
                inset 0 1px 0 rgba(255, 255, 255, 0.25);
            border: 1px solid rgba(255, 255, 255, 0.20);
            color: #FFFFFF;
        }
        .inpower-hero-wave {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            pointer-events: none;
            opacity: 0.22;
            z-index: 0;
        }
        .inpower-hero-grid {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 24px;
            flex-wrap: wrap;
            position: relative;
            z-index: 1;
        }
        .inpower-hero-left {
            display: flex;
            align-items: center;
            gap: 22px;
            flex: 1 1 620px;
        }
        .inpower-logo-box {
            flex-shrink: 0;
            background: rgba(255, 255, 255, 0.10);
            backdrop-filter: blur(12px);
            padding: 6px 10px;
            border-radius: 16px;
            border: 1px solid rgba(255, 255, 255, 0.26);
            box-shadow: 0 10px 24px rgba(15, 23, 42, 0.32);
        }
        .inpower-hero-title-wrap {
            display: flex;
            flex-direction: column;
            gap: 6px;
        }
        .inpower-eyebrow {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            font-size: 0.80rem;
            font-weight: 700;
            letter-spacing: 0.06em;
            color: #BAE6FD;
        }
        .inpower-hero-heading {
            font-size: 1.58rem;
            font-weight: 800;
            color: #FFFFFF;
            margin: 0;
            line-height: 1.25;
            letter-spacing: 0.01em;
        }
        .inpower-hero-sub {
            font-size: 0.90rem;
            color: #E2E8F0;
            margin: 0;
            line-height: 1.5;
        }
        .inpower-pill-row {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 8px;
        }
        .inpower-gov-pill {
            display: inline-flex;
            align-items: center;
            gap: 5px;
            padding: 4px 12px;
            border-radius: 999px;
            font-size: 0.78rem;
            font-weight: 600;
            background: rgba(255, 255, 255, 0.14);
            backdrop-filter: blur(8px);
            border: 1px solid rgba(255, 255, 255, 0.26);
            color: #F8FAFC;
            box-shadow: 0 2px 8px rgba(15, 23, 42, 0.15);
        }
        .inpower-hero-status-box {
            display: flex;
            flex-direction: column;
            gap: 8px;
            min-width: 250px;
            background: rgba(15, 23, 42, 0.38);
            backdrop-filter: blur(12px);
            border: 1px solid rgba(255, 255, 255, 0.22);
            border-radius: 14px;
            padding: 12px 16px;
        }
        .inpower-status-line {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 10px;
            font-size: 0.80rem;
            color: #CBD5E1;
        }
        .inpower-status-val {
            font-weight: 700;
            color: #FFFFFF;
            background: rgba(255, 255, 255, 0.14);
            padding: 2px 9px;
            border-radius: 999px;
            font-size: 0.76rem;
        }

        /* ==========================================================================
           3. 六大功能頁籤：膠囊分段式導覽列 (Segmented Pill Tabs)
           ========================================================================== */
        div[data-testid="stTabs"] > div[role="tablist"] {
            background: rgba(226, 232, 240, 0.78) !important;
            backdrop-filter: blur(12px) !important;
            padding: 7px 9px !important;
            border-radius: 16px !important;
            border: 1px solid rgba(30, 78, 121, 0.18) !important;
            gap: 6px !important;
            box-shadow: inset 0 2px 5px rgba(15, 23, 42, 0.06) !important;
            margin-bottom: 14px !important;
            overflow-x: auto !important;
        }
        div[data-testid="stTabs"] button[role="tab"] {
            border-radius: 11px !important;
            padding: 9px 15px !important;
            font-weight: 600 !important;
            font-size: 0.90rem !important;
            color: #334155 !important;
            background: transparent !important;
            border: 1px solid transparent !important;
            transition: all 0.22s cubic-bezier(0.4, 0, 0.2, 1) !important;
            white-space: nowrap !important;
        }
        div[data-testid="stTabs"] button[role="tab"]:hover {
            background: rgba(255, 255, 255, 0.78) !important;
            color: #1E4E79 !important;
            transform: translateY(-1px) !important;
        }
        div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
            background: linear-gradient(135deg, #162238 0%, #1E4E79 55%, #2563EB 100%) !important;
            color: #FFFFFF !important;
            font-weight: 700 !important;
            border: 1px solid rgba(255, 255, 255, 0.28) !important;
            box-shadow:
                0 6px 16px -3px rgba(37, 99, 235, 0.42),
                0 0 10px rgba(56, 189, 248, 0.28) !important;
            transform: translateY(-1px) !important;
        }
        div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] p {
            color: #FFFFFF !important;
            font-weight: 700 !important;
        }
        div[data-testid="stTabs"] div[data-baseweb="tab-highlight"],
        div[data-testid="stTabs"] div[data-baseweb="tab-border"] {
            display: none !important;
        }

        /* ==========================================================================
           4. 圓角立體色帶 KPI 指標卡 (3D Ribbon Glassmorphic Metric Cards)
           ========================================================================== */
        div[data-testid="stMetric"] {
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.95) 0%, rgba(248, 250, 252, 0.88) 100%) !important;
            backdrop-filter: blur(14px) !important;
            border-radius: 15px !important;
            padding: 15px 18px !important;
            border: 1px solid rgba(30, 78, 121, 0.15) !important;
            border-top: 4px solid #1E4E79 !important;
            box-shadow:
                0 10px 24px -8px rgba(15, 23, 42, 0.08),
                0 2px 6px rgba(30, 78, 121, 0.05) !important;
            transition: all 0.22s ease !important;
        }
        div[data-testid="stMetric"]:hover {
            transform: translateY(-3px) !important;
            border-top-color: #2563EB !important;
            box-shadow:
                0 14px 28px -6px rgba(37, 99, 235, 0.18),
                0 0 12px rgba(59, 130, 246, 0.15) !important;
        }
        div[data-testid="stMetricLabel"] p {
            font-size: 0.84rem !important;
            font-weight: 700 !important;
            color: #475569 !important;
        }
        div[data-testid="stMetricValue"] {
            font-size: 1.65rem !important;
            font-weight: 800 !important;
            color: #162238 !important;
        }

        /* ==========================================================================
           5. 玻璃擬態容器與折疊面板 (Glassmorphic Containers & Expanders)
           ========================================================================== */
        div[data-testid="stVerticalBlockBorderWrapper"] {
            background: rgba(255, 255, 255, 0.86) !important;
            backdrop-filter: blur(12px) !important;
            border-radius: 16px !important;
            border: 1px solid rgba(30, 78, 121, 0.16) !important;
            box-shadow: 0 8px 24px -8px rgba(15, 23, 42, 0.07) !important;
            transition: box-shadow 0.2s ease, transform 0.2s ease !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:hover {
            box-shadow: 0 12px 28px -6px rgba(30, 78, 121, 0.13) !important;
        }

        div[data-testid="stExpander"] {
            background: rgba(255, 255, 255, 0.88) !important;
            backdrop-filter: blur(10px) !important;
            border-radius: 14px !important;
            border: 1px solid rgba(30, 78, 121, 0.16) !important;
            box-shadow: 0 4px 14px rgba(15, 23, 42, 0.05) !important;
            overflow: hidden !important;
            margin-bottom: 10px !important;
        }
        div[data-testid="stExpander"] details summary {
            background: linear-gradient(90deg, rgba(241, 245, 249, 0.85) 0%, rgba(255, 255, 255, 0.90) 100%) !important;
            padding: 10px 16px !important;
            font-weight: 700 !important;
            color: #162238 !important;
        }
        div[data-testid="stExpander"] details summary:hover {
            background: linear-gradient(90deg, rgba(226, 232, 240, 0.75) 0%, rgba(241, 245, 249, 0.95) 100%) !important;
            color: #1E4E79 !important;
        }

        /* ==========================================================================
           6. 霓虹微光四色燈號與結構化治理徽章卡片 (Neon Traffic Lights & Governance Badges)
           ========================================================================== */
        .neon-traffic-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(160px, 1fr));
            gap: 12px;
            margin: 10px 0 16px 0;
        }
        @media (max-width: 900px) {
            .neon-traffic-grid {
                grid-template-columns: repeat(2, 1fr);
            }
        }
        .neon-light-card {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 12px 16px;
            border-radius: 14px;
            backdrop-filter: blur(12px);
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }
        .neon-light-card:hover {
            transform: translateY(-2px);
        }
        .neon-light-red {
            background: linear-gradient(135deg, rgba(254, 242, 242, 0.95) 0%, rgba(254, 226, 226, 0.88) 100%);
            border: 1px solid rgba(239, 68, 68, 0.45);
            border-left: 5px solid #EF4444;
            box-shadow: 0 4px 16px rgba(239, 68, 68, 0.18), 0 0 10px rgba(239, 68, 68, 0.12);
            color: #991B1B;
        }
        .neon-light-yellow {
            background: linear-gradient(135deg, rgba(255, 251, 235, 0.95) 0%, rgba(254, 243, 199, 0.88) 100%);
            border: 1px solid rgba(245, 158, 11, 0.45);
            border-left: 5px solid #F59E0B;
            box-shadow: 0 4px 16px rgba(245, 158, 11, 0.18), 0 0 10px rgba(245, 158, 11, 0.12);
            color: #92400E;
        }
        .neon-light-blue {
            background: linear-gradient(135deg, rgba(239, 246, 255, 0.95) 0%, rgba(219, 234, 254, 0.88) 100%);
            border: 1px solid rgba(59, 130, 246, 0.45);
            border-left: 5px solid #3B82F6;
            box-shadow: 0 4px 16px rgba(59, 130, 246, 0.18), 0 0 10px rgba(59, 130, 246, 0.12);
            color: #1E40AF;
        }
        .neon-light-green {
            background: linear-gradient(135deg, rgba(236, 253, 245, 0.95) 0%, rgba(209, 250, 229, 0.88) 100%);
            border: 1px solid rgba(16, 185, 129, 0.45);
            border-left: 5px solid #10B981;
            box-shadow: 0 4px 16px rgba(16, 185, 129, 0.18), 0 0 10px rgba(16, 185, 129, 0.12);
            color: #065F46;
        }
        .neon-light-title {
            font-size: 0.85rem;
            font-weight: 800;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .neon-light-desc {
            font-size: 0.73rem;
            opacity: 0.86;
            margin-top: 2px;
        }
        .neon-light-count {
            font-size: 1.55rem;
            font-weight: 900;
            line-height: 1;
        }

        /* 待辦事項卡片：左側四色霓虹燈條 + 彩色膠囊徽章列 */
        .inp-action-strip {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            justify-content: space-between;
            gap: 10px;
            padding: 11px 15px;
            border-radius: 12px;
            margin-bottom: 10px;
            backdrop-filter: blur(10px);
        }
        .inp-strip-red {
            background: linear-gradient(90deg, rgba(254, 226, 226, 0.65) 0%, rgba(255, 255, 255, 0.92) 100%);
            border: 1px solid rgba(239, 68, 68, 0.32);
            border-left: 6px solid #EF4444;
            box-shadow: 0 3px 12px rgba(239, 68, 68, 0.12);
        }
        .inp-strip-yellow {
            background: linear-gradient(90deg, rgba(254, 243, 199, 0.68) 0%, rgba(255, 255, 255, 0.92) 100%);
            border: 1px solid rgba(245, 158, 11, 0.35);
            border-left: 6px solid #F59E0B;
            box-shadow: 0 3px 12px rgba(245, 158, 11, 0.12);
        }
        .inp-strip-blue {
            background: linear-gradient(90deg, rgba(219, 234, 254, 0.68) 0%, rgba(255, 255, 255, 0.92) 100%);
            border: 1px solid rgba(59, 130, 246, 0.32);
            border-left: 6px solid #3B82F6;
            box-shadow: 0 3px 12px rgba(59, 130, 246, 0.12);
        }
        .inp-strip-green {
            background: linear-gradient(90deg, rgba(209, 250, 229, 0.68) 0%, rgba(255, 255, 255, 0.92) 100%);
            border: 1px solid rgba(16, 185, 129, 0.35);
            border-left: 6px solid #10B981;
            box-shadow: 0 3px 12px rgba(16, 185, 129, 0.12);
        }
        .inp-badge-group {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 6px;
        }
        .inp-badge {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            padding: 3px 10px;
            border-radius: 999px;
            font-size: 0.76rem;
            font-weight: 700;
            line-height: 1.35;
        }
        .inp-badge-light-red {
            background: #FEE2E2;
            color: #991B1B;
            border: 1px solid #FCA5A5;
            box-shadow: 0 0 8px rgba(239, 68, 68, 0.25);
        }
        .inp-badge-light-yellow {
            background: #FEF3C7;
            color: #92400E;
            border: 1px solid #FCD34D;
            box-shadow: 0 0 8px rgba(245, 158, 11, 0.25);
        }
        .inp-badge-light-blue {
            background: #DBEAFE;
            color: #1E40AF;
            border: 1px solid #93C5FD;
            box-shadow: 0 0 8px rgba(59, 130, 246, 0.22);
        }
        .inp-badge-light-green {
            background: #D1FAE5;
            color: #065F46;
            border: 1px solid #6EE7B7;
            box-shadow: 0 0 8px rgba(16, 185, 129, 0.25);
        }
        .inp-badge-raci-a {
            background: linear-gradient(135deg, #162238 0%, #1E4E79 100%);
            color: #FFFFFF;
            border: 1px solid rgba(255, 255, 255, 0.2);
        }
        .inp-badge-raci-r {
            background: #F1F5F9;
            color: #334155;
            border: 1px solid #CBD5E1;
        }
        .inp-badge-smart {
            background: #EEF2FF;
            color: #3730A3;
            border: 1px solid #C7D2FE;
        }
        .inp-badge-dept {
            background: #F0F9FF;
            color: #0369A1;
            border: 1px solid #BAE6FD;
        }
        .inp-badge-due {
            background: #F8FAFC;
            color: #0F172A;
            border: 1px solid #CBD5E1;
        }
        .inp-badge-qcdt-ok {
            background: #ECFDF5;
            color: #047857;
            border: 1px solid #A7F3D0;
        }
        .inp-badge-qcdt-wait {
            background: #FFFBEB;
            color: #B45309;
            border: 1px solid #FDE68A;
        }

        /* ==========================================================================
           7. 表單輸入框、上傳虛線框、漸層按鈕與斑馬紋表格 (Inputs, Uploaders, Buttons)
           ========================================================================== */
        div[data-testid="stButton"] > button[kind="primary"] {
            background: linear-gradient(135deg, #162238 0%, #1E4E79 50%, #2563EB 100%) !important;
            color: #FFFFFF !important;
            border: 1px solid rgba(255, 255, 255, 0.24) !important;
            border-radius: 11px !important;
            font-weight: 700 !important;
            padding: 0.55rem 1.2rem !important;
            box-shadow: 0 6px 16px -3px rgba(30, 78, 121, 0.40) !important;
            transition: all 0.2s ease !important;
        }
        div[data-testid="stButton"] > button[kind="primary"]:hover {
            background: linear-gradient(135deg, #1E4E79 0%, #2563EB 60%, #3B82F6 100%) !important;
            box-shadow:
                0 10px 22px -3px rgba(37, 99, 235, 0.52),
                0 0 14px rgba(56, 189, 248, 0.40) !important;
            transform: translateY(-1px) !important;
        }
        div[data-testid="stButton"] > button[kind="secondary"],
        div[data-testid="stDownloadButton"] > button {
            background: rgba(255, 255, 255, 0.92) !important;
            color: #162238 !important;
            border: 1px solid rgba(30, 78, 121, 0.25) !important;
            border-radius: 10px !important;
            font-weight: 600 !important;
            box-shadow: 0 2px 6px rgba(15, 23, 42, 0.05) !important;
            transition: all 0.18s ease !important;
        }
        div[data-testid="stButton"] > button[kind="secondary"]:hover,
        div[data-testid="stDownloadButton"] > button:hover {
            border-color: #2563EB !important;
            color: #1E4E79 !important;
            background: #F0F7FF !important;
            box-shadow: 0 4px 12px rgba(37, 99, 235, 0.15) !important;
            transform: translateY(-1px) !important;
        }

        /* 檔案上傳虛線高亮框 */
        section[data-testid="stFileUploaderDropzone"] {
            background: linear-gradient(180deg, rgba(240, 249, 255, 0.72) 0%, rgba(248, 250, 252, 0.92) 100%) !important;
            border: 2px dashed rgba(37, 99, 235, 0.42) !important;
            border-radius: 14px !important;
            transition: all 0.2s ease !important;
        }
        section[data-testid="stFileUploaderDropzone"]:hover {
            border-color: #1E4E79 !important;
            background: rgba(224, 242, 254, 0.55) !important;
            box-shadow: 0 0 14px rgba(37, 99, 235, 0.14) !important;
        }

        /* 文字輸入框、文字區域與下拉選單 Focus 光暈 */
        div[data-baseweb="input"] > div,
        div[data-baseweb="textarea"] > div,
        div[data-baseweb="select"] > div {
            border-radius: 10px !important;
            border-color: rgba(148, 163, 184, 0.45) !important;
            background-color: rgba(255, 255, 255, 0.95) !important;
            transition: border-color 0.18s ease, box-shadow 0.18s ease !important;
        }
        div[data-baseweb="input"] > div:focus-within,
        div[data-baseweb="textarea"] > div:focus-within,
        div[data-baseweb="select"] > div:focus-within {
            border-color: #2563EB !important;
            box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.18) !important;
        }

        /* 資料表圓角與立體邊框 */
        div[data-testid="stDataFrame"] {
            border-radius: 14px !important;
            overflow: hidden !important;
            border: 1px solid rgba(30, 78, 121, 0.18) !important;
            box-shadow: 0 6px 18px -6px rgba(15, 23, 42, 0.08) !important;
        }

        /* ==========================================================================
           8. 側邊欄模組化狀態卡片 (Modular Sidebar Status Cards)
           ========================================================================== */
        section[data-testid="stSidebar"] {
            background: linear-gradient(180deg, #F1F5F9 0%, #E8EEF6 50%, #F8FAFC 100%) !important;
            border-right: 1px solid rgba(30, 78, 121, 0.16) !important;
        }
        .inp-sb-card {
            background: rgba(255, 255, 255, 0.88);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(30, 78, 121, 0.16);
            border-left: 4px solid #1E4E79;
            border-radius: 12px;
            padding: 10px 13px;
            margin: 8px 0;
            box-shadow: 0 4px 10px rgba(15, 23, 42, 0.05);
        }
        .inp-sb-card-title {
            font-size: 0.78rem;
            font-weight: 800;
            color: #475569;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            margin-bottom: 4px;
        }
        .inp-sb-card-value {
            font-size: 0.90rem;
            font-weight: 700;
            color: #162238;
        }
        .inp-sb-card-sub {
            font-size: 0.75rem;
            color: #64748B;
            margin-top: 2px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_corporate_hero_header(
    storage_mode_label: str,
    active_model: str,
    total_meetings: int,
    total_actions: int,
) -> None:
    """渲染頂部『INPOWER 銓泰環能科技』漸層商務橫幅 (Hero Header Card + 企業波浪底紋)."""
    logo_svg = get_inpower_logo_svg(width=226, height=88, compact=False)
    safe_storage = html.escape(storage_mode_label)
    safe_model = html.escape(active_model)

    st.markdown(
        f"""
        <div class="inpower-hero-card">
            <svg class="inpower-hero-wave" viewBox="0 0 1440 220" preserveAspectRatio="none">
                <path d="M0,36 C320,125 640,-25 1020,58 C1240,104 1360,40 1440,22 L1440,0 L0,0 Z" fill="#FFFFFF"/>
                <path d="M0,78 C350,165 690,12 1060,92 C1260,136 1380,82 1440,62 L1440,24 C1360,42 1240,104 1020,58 C640,-25 320,125 0,36 Z" fill="#0F172A"/>
            </svg>
            <div class="inpower-hero-grid">
                <div class="inpower-hero-left">
                    <div class="inpower-logo-box">
                        {logo_svg}
                    </div>
                    <div class="inpower-hero-title-wrap">
                        <div class="inpower-eyebrow">⚡ INPOWER 銓泰環能科技 · 企業級 AI 會議治理中樞</div>
                        <div class="inpower-hero-heading">🛡️ AI 會議記錄管理 Web App</div>
                        <p class="inpower-hero-sub">
                            透過 <b>Google Gemini Structured Outputs</b> 自動萃取決策與行動方案，深度落實
                            <b>RACI 單一當責制</b>、<b>SMART 四階目標分層</b> 與 <b>QCD+T 真實性成果佐證閉環</b>。
                        </p>
                        <div class="inpower-pill-row">
                            <span class="inpower-gov-pill">👑 RACI 唯一當責者 (A)</span>
                            <span class="inpower-gov-pill">🎯 SMART 四階層級</span>
                            <span class="inpower-gov-pill">🛡️ QCD+T 結案實證閉環</span>
                            <span class="inpower-gov-pill">🚦 四色霓虹燈號預警</span>
                            <span class="inpower-gov-pill">📥 17 欄公版零失真直通車</span>
                        </div>
                    </div>
                </div>
                <div class="inpower-hero-status-box">
                    <div class="inpower-status-line">
                        <span>🗄️ 雙模儲存引擎</span>
                        <span class="inpower-status-val">{safe_storage}</span>
                    </div>
                    <div class="inpower-status-line">
                        <span>🤖 AI 萃取模型</span>
                        <span class="inpower-status-val">{safe_model}</span>
                    </div>
                    <div class="inpower-status-line">
                        <span>📊 即時納管規模</span>
                        <span class="inpower-status-val">{total_meetings} 場會議 · {total_actions} 項任務</span>
                    </div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_traffic_light_neon_strip(light_counts: dict[str, int]) -> None:
    """渲染四色霓虹微光燈號預警卡片列 (紅/黃/藍/綠燈)."""
    red_c = light_counts.get("🔴 紅燈", 0)
    yel_c = light_counts.get("🟡 黃燈", 0)
    blu_c = light_counts.get("🔵 藍燈", 0)
    grn_c = light_counts.get("🟢 綠燈", 0)

    st.markdown(
        f"""
        <div class="neon-traffic-grid">
            <div class="neon-light-card neon-light-red">
                <div>
                    <div class="neon-light-title">🔴 紅燈預警 (高風險)</div>
                    <div class="neon-light-desc">🚨 逾期未完成 ／ 🛑 執行受阻</div>
                </div>
                <div class="neon-light-count">{red_c}</div>
            </div>
            <div class="neon-light-card neon-light-yellow">
                <div>
                    <div class="neon-light-title">🟡 黃燈預警 (需關注)</div>
                    <div class="neon-light-desc">⚠️ 治理缺口 ／ ⏳ 3日內到期</div>
                </div>
                <div class="neon-light-count">{yel_c}</div>
            </div>
            <div class="neon-light-card neon-light-blue">
                <div>
                    <div class="neon-light-title">🔵 藍燈推進 (進行中)</div>
                    <div class="neon-light-desc">⏳ 未完成 ／ 期限內合規推進</div>
                </div>
                <div class="neon-light-count">{blu_c}</div>
            </div>
            <div class="neon-light-card neon-light-green">
                <div>
                    <div class="neon-light-title">🟢 綠燈閉環 (已完成)</div>
                    <div class="neon-light-desc">✅ 已完成 (Done) ＋ 具 T 佐證</div>
                </div>
                <div class="neon-light-count">{grn_c}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_action_governance_strip(
    act: ActionItem,
    traffic_light: str,
    gov_status: str,
) -> None:
    """為單筆待辦事項渲染左側四色燈號邊條與 RACI / SMART / QCD+T 結構化彩色膠囊徽章列."""
    if "🔴" in traffic_light:
        strip_cls = "inp-strip-red"
        light_badge_cls = "inp-badge-light-red"
    elif "🟡" in traffic_light:
        strip_cls = "inp-strip-yellow"
        light_badge_cls = "inp-badge-light-yellow"
    elif "🟢" in traffic_light:
        strip_cls = "inp-strip-green"
        light_badge_cls = "inp-badge-light-green"
    else:
        strip_cls = "inp-strip-blue"
        light_badge_cls = "inp-badge-light-blue"

    acc = html.escape(act.raci.accountable or "待指定")
    resp = html.escape(", ".join(act.raci.responsible) or "待指定")
    smart_lvl = html.escape(act.smart.hierarchy_level)
    dept = html.escape(act.department or "跨部門")
    due = html.escape(act.due_date or "待定")
    light_txt = html.escape(f"{traffic_light} · {gov_status}")

    has_ev = bool(act.qcdt.evidence_submitted and act.qcdt.evidence_submitted.strip())
    qcdt_cls = "inp-badge-qcdt-ok" if has_ev else "inp-badge-qcdt-wait"
    qcdt_txt = "✅ T 佐證已提交" if has_ev else "⏳ T 佐證待提交"

    st.markdown(
        f"""
        <div class="inp-action-strip {strip_cls}">
            <div class="inp-badge-group">
                <span class="inp-badge {light_badge_cls}">🚦 {light_txt}</span>
                <span class="inp-badge inp-badge-raci-a">👑 A 當責：{acc}</span>
                <span class="inp-badge inp-badge-raci-r">🛠️ R 執行：{resp}</span>
            </div>
            <div class="inp-badge-group">
                <span class="inp-badge inp-badge-smart">🏷️ {smart_lvl}</span>
                <span class="inp-badge inp-badge-dept">🏢 {dept}</span>
                <span class="inp-badge inp-badge-due">📅 D 期限：{due}</span>
                <span class="inp-badge {qcdt_cls}">{qcdt_txt}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar_status_card(title: str, value: str, subtitle: str = "", accent_color: str = "#1E4E79") -> None:
    """於側邊欄渲染模組化玻璃擬態狀態卡片."""
    safe_title = html.escape(title)
    safe_val = html.escape(value)
    safe_sub = html.escape(subtitle)
    sub_html = f'<div class="inp-sb-card-sub">{safe_sub}</div>' if safe_sub else ""
    st.markdown(
        f"""
        <div class="inp-sb-card" style="border-left-color: {accent_color};">
            <div class="inp-sb-card-title">{safe_title}</div>
            <div class="inp-sb-card-value">{safe_val}</div>
            {sub_html}
        </div>
        """,
        unsafe_allow_html=True,
    )
