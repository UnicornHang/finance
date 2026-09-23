import type { Config } from 'tailwindcss'

/**
 * 现代 AI Agent 设计系统 (Modern AI Agent)
 *
 * 设计原则 (vs. 上一版 Pristine Crisp Fintech):
 * - 柔和边角: 圆角整体上调一档 (控件 6 / 卡片 12 / 弹窗 16)
 * - 软染色投影: 用低透明度 + 略大模糊替代硬边阴影
 * - 现代字体: Inter (主) + JetBrains Mono (等宽)
 * - 平滑缓动: smooth/snappy 替代线性 / 标准 cubic-bezier
 *
 * 设计 Token 速查:
 * - 圆角: sm 4 / md 8 / lg 12 / xl 16 / 2xl 20
 * - 投影: hairline / soft / elevated / glow-primary
 * - 字体: Inter (sans) + JetBrains Mono (mono)
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
        canvas: '#f7f8fb', // 应用背景 (Soft Mist)
        surface: {
          DEFAULT: '#ffffff', // 卡片/容器主表面
          inset: '#f3f5f9', // 二级内嵌表面
          muted: '#f7f8fb', // 表格 / 表面板
        },

        // ===== 文本层级 =====
        ink: {
          DEFAULT: '#0b1220', // Primary Text - Deep Slate
          secondary: '#3b475c', // Mid Slate
          tertiary: '#6b7691', // Soft Slate
          muted: '#aab3c5', // Disabled / Placeholder
          inverse: '#ffffff',
        },

        // ===== 结构边框 =====
        line: {
          DEFAULT: '#e6e9f0', // Primary Structural Border (柔和)
          subtle: '#f1f3f7', // Hairline Subtle Border
          strong: '#d4d9e3', // Hover Border / Raised Border
          focus: '#0284c7', // Focused Element Border
        },

        // ===== 主色 - AI Agent Cerulean (略调亮，更通透) =====
        primary: {
          DEFAULT: '#0ea5e9',
          hover: '#0284c7',
          active: '#0369a1',
          tint: '#f0f9ff',
          border: '#bae6fd',
          focus: '#bae6fd',
          foreground: '#ffffff',
        },

        // ===== 成功 / Jade =====
        success: {
          DEFAULT: '#10b981',
          tint: '#ecfdf5',
          border: '#a7f3d0',
          foreground: '#047857',
        },

        // ===== 警示 / Crimson =====
        danger: {
          DEFAULT: '#ef4444',
          hover: '#dc2626',
          tint: '#fef2f2',
          border: '#fecaca',
          foreground: '#b91c1c',
        },

        // ===== 警告 / Amber =====
        warning: {
          DEFAULT: '#f59e0b',
          tint: '#fffbeb',
          border: '#fde68a',
          foreground: '#b45309',
        },

        // ===== Neutral / Draft =====
        neutral: {
          DEFAULT: '#475569',
          tint: '#f7f8fb',
          border: '#e6e9f0',
          foreground: '#475569',
        },

        // shadcn/ui 兼容别名
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
          'Inter',
          '-apple-system',
          'BlinkMacSystemFont',
          '"Segoe UI"',
          'Roboto',
          '"PingFang SC"',
          '"Hiragino Sans GB"',
          '"Microsoft YaHei"',
          'sans-serif',
        ],
        mono: [
          '"JetBrains Mono"',
          'ui-monospace',
          'SFMono-Regular',
          'Menlo',
          'Monaco',
          'Consolas',
          'monospace',
        ],
      },
      fontSize: {
        'display-lg': ['44px', { lineHeight: '52px', letterSpacing: '-0.03em', fontWeight: '700' }],
        'headline-lg': ['32px', { lineHeight: '40px', letterSpacing: '-0.02em', fontWeight: '600' }],
        'headline-md': ['24px', { lineHeight: '30px', letterSpacing: '-0.015em', fontWeight: '600' }],
        'headline-sm': ['18px', { lineHeight: '26px', letterSpacing: '-0.01em', fontWeight: '600' }],
        'title-lg': ['16px', { lineHeight: '24px', letterSpacing: '-0.005em', fontWeight: '600' }],
        'body-lg': ['16px', { lineHeight: '24px', letterSpacing: '0em', fontWeight: '400' }],
        'body-md': ['14px', { lineHeight: '20px', letterSpacing: '0em', fontWeight: '400' }],
        'body-sm': ['13px', { lineHeight: '18px', letterSpacing: '0em', fontWeight: '400' }],
        'label-md': ['12px', { lineHeight: '16px', letterSpacing: '0.02em', fontWeight: '600' }],
        'label-sm': ['11px', { lineHeight: '14px', letterSpacing: '0.03em', fontWeight: '600' }],
        'numeric-lg': ['28px', { lineHeight: '32px', letterSpacing: '-0.02em', fontWeight: '600' }],
        'numeric-md': ['15px', { lineHeight: '20px', letterSpacing: '-0.01em', fontWeight: '600' }],
      },
      borderRadius: {
        // 升级圆角 token: 控件 6 / 卡片 12 / 弹窗 16 / 大弹窗 20
        sm: '0.25rem', // 4px - chip / 标签
        DEFAULT: '0.375rem', // 6px - 按钮 / 输入
        md: '0.5rem', // 8px - 控件
        lg: '0.75rem', // 12px - 卡片
        xl: '1rem', // 16px - 弹窗 / Sheet
        '2xl': '1.25rem', // 20px - 大弹窗
        '3xl': '1.5rem', // 24px - 全屏弹层
        full: '9999px',
      },
      spacing: {
        gutter: '1.5rem',
        'gutter-mobile': '0.75rem',
        margin: '2rem',
        'margin-mobile': '1rem',
      },
      boxShadow: {
        // 软染色投影 - 现代 AI 产品主流 (低透明度 + 略大模糊)
        hairline: '0 0 0 1px rgb(230 233 240)', // 1px 边框模拟
        soft: '0 1px 2px 0 rgba(15, 23, 42, 0.04), 0 1px 3px 0 rgba(15, 23, 42, 0.06)',
        // 弹层 / 菜单 / 模态 - 比原 raised 更通透
        elevated:
          '0 4px 6px -1px rgba(15, 23, 42, 0.06), 0 12px 24px -6px rgba(15, 23, 42, 0.10), 0 0 0 1px rgba(15, 23, 42, 0.04)',
        // 主色光晕 - 焦点/激活态使用
        'glow-primary':
          '0 0 0 4px rgba(14, 165, 233, 0.12), 0 4px 12px -2px rgba(14, 165, 233, 0.20)',
        // 向后兼容别名 (旧组件仍引用 shadow-raised 时不会破坏构建)
        raised:
          '0 4px 6px -1px rgba(15, 23, 42, 0.06), 0 12px 24px -6px rgba(15, 23, 42, 0.10)',
      },
      transitionTimingFunction: {
        // 平滑缓动 (现代 AI 产品主流)
        smooth: 'cubic-bezier(0.32, 0.72, 0, 1)',
        snappy: 'cubic-bezier(0.22, 1, 0.36, 1)',
        soft: 'cubic-bezier(0.4, 0, 0.2, 1)',
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
        'fade-in': {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
        'slide-up': {
          from: { opacity: '0', transform: 'translateY(8px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        'scale-in': {
          from: { opacity: '0', transform: 'scale(0.96)' },
          to: { opacity: '1', transform: 'scale(1)' },
        },
      },
      animation: {
        'pulse-soft': 'pulse-soft 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'stream-blink': 'stream-blink 1s steps(1) infinite',
        'fade-in': 'fade-in 200ms cubic-bezier(0.32, 0.72, 0, 1) both',
        'slide-up': 'slide-up 280ms cubic-bezier(0.32, 0.72, 0, 1) both',
        'scale-in': 'scale-in 200ms cubic-bezier(0.32, 0.72, 0, 1) both',
      },
    },
  },
  plugins: [require('tailwindcss-animate')],
} satisfies Config
