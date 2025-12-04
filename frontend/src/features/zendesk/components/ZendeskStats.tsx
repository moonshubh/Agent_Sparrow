"use client"

import { useRef } from "react"
import { motion, useInView } from "motion/react"

export type ZendeskHealth = {
  enabled?: boolean
  dry_run?: boolean
  provider?: string
  model?: string
  usage?: { calls_used?: number; budget?: number } | null
  daily?: { gemini_calls_used?: number; gemini_daily_limit?: number } | null
  queue?: { pending?: number; retry?: number; processing?: number; failed?: number } | null
}

interface StatsGridProps {
  title?: string
  description?: string
  health: ZendeskHealth
}

export function ZendeskStats({
  title = "Zendesk — Integration Health",
  description = "Feature status, usage, and queue metrics",
  health,
}: StatsGridProps) {
  const ref = useRef(null)
  const isInView = useInView(ref, { once: true })

  const enabled = health?.enabled ? "On" : "Off"
  const dryRun = health?.dry_run ? "On" : "Off"
  const dailyUsed = health?.daily?.gemini_calls_used ?? 0
  const dailyLimit = health?.daily?.gemini_daily_limit ?? 0
  const monthlyUsed = health?.usage?.calls_used ?? 0
  const monthlyBudget = health?.usage?.budget ?? 0
  const qPending = health?.queue?.pending ?? 0
  const qFailed = health?.queue?.failed ?? 0

  const stats = [
    { value: enabled, label: "Feature" },
    { value: dryRun, label: "Dry run" },
    { value: `${dailyUsed}/${dailyLimit}`.trim(), label: "Calls today" },
    { value: `${monthlyUsed}/${monthlyBudget}`.trim(), label: "Calls this month" },
    { value: String(qPending), label: "Pending tickets" },
    { value: String(qFailed), label: "Failed tickets" },
  ]

  return (
    <section className="py-4">
      <div className="mx-auto max-w-7xl px-0">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          viewport={{ once: true }}
          className="mb-4 text-left"
        >
          <h2 className="text-foreground mb-1 text-xl font-bold lg:text-2xl">
            {title}
          </h2>
          <p className="text-foreground/70 max-w-2xl text-sm">
            {description}
          </p>
        </motion.div>

        <div
          ref={ref}
          className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3"
        >
          {stats.map((stat, index) => (
            <motion.div
              key={stat.label}
              initial={{ opacity: 0, y: 30 }}
              animate={isInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 30 }}
              transition={{ duration: 0.6, delay: index * 0.06 }}
              className="group border-border bg-background hover:border-brand relative overflow-hidden rounded-xl border p-5 text-left transition-all hover:shadow-lg"
            >
              <motion.div
                className="text-brand mb-1 text-3xl font-bold lg:text-4xl"
                initial={{ scale: 0.5 }}
                animate={isInView ? { scale: 1 } : { scale: 0.5 }}
                transition={{ duration: 0.8, delay: index * 0.06 + 0.2, type: "spring", stiffness: 200 }}
              >
                {stat.value}
              </motion.div>
              <h3 className="text-foreground text-sm font-medium">
                {stat.label}
              </h3>

              <motion.div
                className="from-brand/5 absolute inset-0 bg-gradient-to-br to-transparent opacity-0 group-hover:opacity-100"
                initial={{ opacity: 0 }}
                whileHover={{ opacity: 1 }}
                transition={{ duration: 0.3 }}
              />
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  )
}
