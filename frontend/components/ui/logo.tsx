export default function Logo({ className = "h-6 w-auto" }) {
  return (
    <svg viewBox="0 0 150 28" className={className} aria-label="Obsidian AI">
      <text
        x="0"
        y="21"
        fontFamily="Geist, Arial, sans-serif"
        fontWeight="700"
        fontSize="20"
        letterSpacing="0.5"
      >
        <tspan fill="currentColor" className="text-foreground">
          OBSIDIAN
        </tspan>
        <tspan fill="currentColor" className="text-muted-foreground" dx="6">
          AI
        </tspan>
      </text>
    </svg>
  )
}
