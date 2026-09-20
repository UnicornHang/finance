import type { Config } from 'tailwindcss'

/**
 * Pristine Crisp Fintech 设计系统
 * 来源: docs/SystemColor.md
 *
 * 设计原则:
 * - 绝对平面 (Flat Stratification)，禁止渐变与重投影
 * - 手术级精度，1px hairline 边框 + 充足留白
 * - 配色克制: 单一冷蓝主色 + 翠绿成功色 + 暗红警示色 + 琥珀警告色
 */
export default {
  darkMode: ['class'],
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    container: {
      center: true,
      padding: '1.5rem',
      screens: { '2xl': '1440px' },
    },
    extend: {
      colors: {
        // ===== 中性画布与表面 =====
        canvas: '#f8fafc', // 应用背景 (Cool Slate Off-White)
        surface: {
          DEFAULT: '#ffffff', // 卡片/容器主表面
          inset: '#f1f5f9', // 二级内嵌表面 (Subtle Flat Ice)
          muted: '#f8fafc', // 表格 / 表面板
        },

        // ===== 文本层级 =====
        ink: {
          DEFAULT: '#0f172a', // Primary Text - Crisp Charcoal Slate
          secondary: '#334155', // Mid Slate
          tertiary: '#64748b', // Soft Slate
          muted: '#94a3b8', // Disabled / Placeholder
          inverse: '#ffffff',
        },

        // ===== 结构边框 =====
        line: {
          DEFAULT: '#e2e8f0', // Primary Structural Border
          subtle: '#f1f5f9', // Hairline Subtle Border
          strong: '#cbd5e1', // Hover Border / Raised Border
          focus: '#0284c7', // Focused Element Border
        },

        // ===== 主色 - Vibrant Cerulean Blue =====
        primary: {
          DEFAULT: '#0284c7',
          hover: '#0369a1',
          active: '#075985',
          tint: '#f0f9ff',
          border: '#bae6fd',
          focus: '#bae6fd',
          foreground: '#ffffff',
        },

        // ===== 成功 / Jade =====
        success: {
          DEFAULT: '#059669',
          tint: '#ecfdf5',
          border: '#a7f3d0',
          foreground: '#059669',
        },

        // ===== 警示 / Crimson =====
        danger: {
          DEFAULT: '#dc2626',
          hover: '#b91c1c',
          tint: '#fef2f2',
          border: '#fecaca',
          foreground: '#dc2626',
        },

        // ===== 警告 / Amber =====
        warning: {
          DEFAULT: '#d97706',
          tint: '#fffbeb',
          border: '#fde68a',
          foreground: '#b45309',
        },

        // ===== Neutral / Draft =====
        neutral: {
          DEFAULT: '#475569',
          tint: '#f8fafc',
          border: '#e2e8f0',
          foreground: '#475569',
        },

        // shadcn/ui 兼容别名 (保留以维持现有组件)
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        secondary: {
          DEFAULT: 'hsl(var(--secondary))',
          foreground: 'hsl(var(--secondary-foreground))',
        },
        destructive: {
          DEFAULT: 'hsl(var(--destructive))',
          foreground: 'hsl(var(--destructive-foreground))',
        },
        muted: {
          DEFAULT: 'hsl(var(--muted))',
          foreground: 'hsl(var(--muted-foreground))',
        },
        accent: {
          DEFAULT: 'hsl(var(--accent))',
          foreground: 'hsl(var(--accent-foreground))',
        },
        card: {
          DEFAULT: 'hsl(var(--card))',
          foreground: 'hsl(var(--card-foreground))',
        },
      },
      fontFamily: {
        sans: [
          '"Plus Jakarta Sans"',
          '-apple-system',
          'BlinkMacSystemFont',
          '"Segoe UI"',
          'Roboto',
          '"PingFang SC"',
          '"Hiragino Sans GB"',
          '"Microsoft YaHei"',
          'sans-serif',
        ],
      },
      fontSize: {
        // 与 SystemColor.md typography 对齐
        'display-lg': ['44px', { lineHeight: '52px', letterSpacing: '-0.03em', fontWeight: '700' }],
        'headline-lg': ['32px', { lineHeight: '40px', letterSpacing: '-0.02em', fontWeight: '600' }],
        'headline-md': ['24px', { lineHeight: '30px', letterSpacing: '-0.015em', fontWeight: '600' }],
        'headline-sm': ['18px', { lineHeight: '24px', letterSpacing: '-0.01em', fontWeight: '600' }],
        'title-lg': ['16px', { lineHeight: '22px', letterSpacing: '-0.005em', fontWeight: '600' }],
        'body-lg': ['16px', { lineHeight: '24px', letterSpacing: '0em', fontWeight: '400' }],
        'body-md': ['14px', { lineHeight: '20px', letterSpacing: '0em', fontWeight: '400' }],
        'body-sm': ['13px', { lineHeight: '18px', letterSpacing: '0em', fontWeight: '400' }],
        'label-md': ['12px', { lineHeight: '16px', letterSpacing: '0.02em', fontWeight: '600' }],
        'label-sm': ['11px', { lineHeight: '14px', letterSpacing: '0.03em', fontWeight: '600' }],
        'numeric-lg': ['28px', { lineHeight: '32px', letterSpacing: '-0.02em', fontWeight: '600' }],
        'numeric-md': ['15px', { lineHeight: '20px', letterSpacing: '-0.01em', fontWeight: '600' }],
      },
      borderRadius: {
        // 与 SystemColor.md rounded 对齐
        sm: '0.125rem', // 2px
        DEFAULT: '0.25rem', // 4px - 控件
        md: '0.375rem', // 6px
        lg: '0.5rem', // 8px - 卡片/容器
        xl: '0.75rem', // 12px
        full: '9999px', // pill
      },
      spacing: {
        // 与 SystemColor.md spacing 对齐
        gutter: '1.5rem', // 24px
        'gutter-mobile': '0.75rem', // 12px
        margin: '2rem', // 32px
        'margin-mobile': '1rem', // 16px
      },
      boxShadow: {
        // 移除重投影，仅保留精确的边缘分隔 (Ultra-crisp, non-diffuse)
        raised:
          '0 4px 12px 0 rgba(15, 23, 42, 0.05), 0 0 0 1px rgb(203 213 225)', // 弹层/菜单/模态
        hairline: '0 0 0 1px rgb(226 232 240)', // 1px border 模拟
      },
      keyframes: {
        'pulse-soft': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.4' },
        },
        'stream-blink': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0' },
        },
      },
      animation: {
        'pulse-soft': 'pulse-soft 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'stream-blink': 'stream-blink 1s steps(1) infinite',
      },
    },
  },
  plugins: [require('tailwindcss-animate')],
} satisfies Config