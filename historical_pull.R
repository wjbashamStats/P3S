#!/usr/bin/env Rscript
# historical_pull.R -- R port of historical_pull.py, for running from a
# network unrestricted from api.the-odds-api.com (Claude's remote sandbox
# for this project is not, per its org's egress policy).
#
# Does the pull AND the flatten in one pass: for each week-1 FBS-vs-FBS
# game, pulls the closing-line historical player-prop odds, checkpoints
# the raw JSON to hist_raw/ (so a crash/rerun never re-spends), and writes
# one tidy CSV -- one row per (game, player, market) with the consensus
# closing line and median over/under price across books. Upload that CSV
# back; no need to upload hist_raw/ itself.
#
# SETUP
#   install.packages(c("httr", "jsonlite"))          # if not already installed
#   Sys.setenv(ODDS_API_KEY = "your_real_key")        # do NOT hardcode it below
#   (or put ODDS_API_KEY=... in a .Renviron in this folder and restart R)
#
# Run from the folder containing 2025_schedule.csv and team_map.csv:
#   Rscript historical_pull.R --week 1 --dry-run     # spends nothing, sanity check
#   Rscript historical_pull.R --week 1               # the real pull
#
# COST MODEL (matches historical_pull.py, same non-negotiable math):
#   historical event-odds = 10 credits x regions x markets x event x snapshot.
#   Closing-only (1 snapshot), 6 markets, 1 region => 60 credits/game.

suppressMessages({
  library(httr)
  library(jsonlite)
})

# Team/player names in the source files have accents (San Jose State) and
# non-ASCII chars (Hawai'i); force a UTF-8 locale so string handling below
# doesn't silently mangle them on a system that defaults to something else.
invisible(try(Sys.setlocale("LC_CTYPE", "C.UTF-8"), silent = TRUE))

# ----------------- CONFIG -----------------
API_KEY <- Sys.getenv("ODDS_API_KEY")
if (!nzchar(API_KEY)) {
  stop("ODDS_API_KEY is not set. Run Sys.setenv(ODDS_API_KEY=\"...\") first (or set it in .Renviron) -- do not hardcode it in this file.")
}
SPORT    <- "americanfootball_ncaaf"
REGION   <- "us"
MARKETS  <- c("player_pass_yds", "player_pass_attempts",
              "player_rush_yds", "player_rush_attempts",
              "player_reception_yds", "player_receptions")
ODDS_FMT <- "american"

HIST_COST_PER  <- 10
CREDIT_CEILING <- 100000
CREDIT_FLOOR   <- 2000
BASE <- "https://api.the-odds-api.com/v4"

SCRIPT_DIR  <- dirname(sub("--file=", "", grep("--file=", commandArgs(trailingOnly = FALSE), value = TRUE)))
if (length(SCRIPT_DIR) == 0 || !nzchar(SCRIPT_DIR)) SCRIPT_DIR <- "."
CKPT_DIR    <- file.path(SCRIPT_DIR, "hist_raw")
SNAPSHOTS   <- c("closing")            # closing-only, per PROJECT_STATE.md decision
SNAPSHOT_OFFSET_HOURS <- c(opening = 36, closing = 1)

FBS_CONF <- c("SEC", "Big Ten", "Big 12", "ACC", "American Athletic",
              "Mountain West", "Sun Belt", "Conference USA", "Mid-American",
              "Pac-12", "FBS Independents")

# ----------------- ARGS -----------------
parse_args <- function(argv) {
  a <- list(schedule = file.path(SCRIPT_DIR, "2025_schedule.csv"),
            team_map = file.path(SCRIPT_DIR, "team_map.csv"),
            season = 2025, week = NA, week_start = NA, week_end = NA,
            season_type = "regular",
            max_games = NA, include_one_fbs = FALSE, dry_run = FALSE,
            out = NA)
  i <- 1
  while (i <= length(argv)) {
    k <- argv[i]
    val <- function() { i <<- i + 1; argv[i] }
    if (k == "--schedule") a$schedule <- val()
    else if (k == "--team-map") a$team_map <- val()
    else if (k == "--season") a$season <- as.integer(val())
    else if (k == "--week") a$week <- as.integer(val())
    else if (k == "--week-start") a$week_start <- as.integer(val())
    else if (k == "--week-end") a$week_end <- as.integer(val())
    else if (k == "--season-type") a$season_type <- val()
    else if (k == "--max-games") a$max_games <- as.integer(val())
    else if (k == "--include-one-fbs") a$include_one_fbs <- TRUE
    else if (k == "--dry-run") a$dry_run <- TRUE
    else if (k == "--out") a$out <- val()
    else stop(paste("unknown arg:", k))
    i <- i + 1
  }
  if (xor(is.na(a$week_start), is.na(a$week_end)))
    stop("--week-start and --week-end must be given together")
  if (!is.na(a$week) && !is.na(a$week_start))
    stop("use --week for a single week OR --week-start/--week-end for a range, not both")
  if (is.na(a$out)) {
    wk <- if (!is.na(a$week_start)) paste0(a$week_start, "-", a$week_end)
          else if (is.na(a$week)) "all" else a$week
    a$out <- file.path(SCRIPT_DIR, paste0("hist_props_closing_wk", wk, ".csv"))
  }
  a
}
args <- parse_args(commandArgs(trailingOnly = TRUE))

# ----------------- SCHEDULE -----------------
load_schedule <- function(path, season, season_type, fbs_only = TRUE, both_fbs = TRUE) {
  df <- read.csv(path, stringsAsFactors = FALSE, fileEncoding = "UTF-8",
                 colClasses = "character")
  names(df) <- trimws(names(df))
  names(df)[1] <- sub("^﻿", "", names(df)[1])         # strip a leading BOM if the reader left one
  df <- df[!duplicated(df$Id), ]                          # dedup: ~87 rows repeated per broadcast outlet
  df <- df[df$Season == as.character(season), ]
  if (season_type != "all") df <- df[df$SeasonType == season_type, ]
  if (fbs_only) {
    h_fbs <- df$HomeConference %in% FBS_CONF
    a_fbs <- df$AwayConference %in% FBS_CONF
    df <- if (both_fbs) df[h_fbs & a_fbs, ] else df[h_fbs | a_fbs, ]
  }
  df <- df[nzchar(df$StartTime), ]
  df$commence_dt <- as.POSIXct(df$StartTime, format = "%Y-%m-%dT%H:%M:%OSZ", tz = "UTC")
  df <- df[order(df$commence_dt), ]
  df
}

snapshot_iso <- function(commence_dt, label) {
  ts <- commence_dt - SNAPSHOT_OFFSET_HOURS[[label]] * 3600
  format(ts, "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
}

# ----------------- TEAM NAME MATCHING -----------------
norm_name <- function(s) {
  s <- iconv(s, from = "UTF-8", to = "ASCII//TRANSLIT")     # strip accents (e.g. Jose -> Jose)
  s <- tolower(ifelse(is.na(s), "", s))
  gsub("[^a-z0-9]", "", s)
}

load_team_map <- function(path) {
  if (!file.exists(path)) return(list())
  df <- read.csv(path, stringsAsFactors = FALSE, fileEncoding = "UTF-8")
  setNames(as.list(norm_name(df$odds_name)), norm_name(df$cfbd_name))
}
team_map <- load_team_map(args$team_map)

apply_map <- function(team) {
  n <- norm_name(team)
  if (!is.null(team_map[[n]])) team_map[[n]] else n
}

match_event <- function(events, home, away) {
  h <- apply_map(home); a <- apply_map(away)
  for (e in events) {
    eh <- norm_name(e$home_team %||% ""); ea <- norm_name(e$away_team %||% "")
    fwd <- (grepl(h, eh, fixed = TRUE) || grepl(eh, h, fixed = TRUE)) &&
           (grepl(a, ea, fixed = TRUE) || grepl(ea, a, fixed = TRUE))
    rev <- (grepl(h, ea, fixed = TRUE) || grepl(ea, h, fixed = TRUE)) &&
           (grepl(a, eh, fixed = TRUE) || grepl(eh, a, fixed = TRUE))
    if (fwd || rev) return(e)
  }
  NULL
}
`%||%` <- function(a, b) if (is.null(a)) b else a

# ----------------- HTTP -----------------
api_get <- function(path, query) {
  resp <- tryCatch(
    GET(paste0(BASE, path), query = c(query, apiKey = API_KEY), timeout(40)),
    error = function(e) { message("  error: ", conditionMessage(e)); NULL }
  )
  if (is.null(resp)) return(list(body = NULL, remaining = NA))
  remaining <- headers(resp)[["x-requests-remaining"]]
  if (http_error(resp)) {
    message("  HTTP ", status_code(resp), ": ", substr(content(resp, "text", encoding = "UTF-8"), 1, 200))
    return(list(body = NULL, remaining = if (is.null(remaining)) NA else as.integer(remaining)))
  }
  body <- fromJSON(content(resp, "text", encoding = "UTF-8"), simplifyVector = FALSE)
  list(body = body, remaining = if (is.null(remaining)) NA else as.integer(remaining))
}

hist_events <- function(date_iso) {
  r <- api_get(paste0("/historical/sports/", SPORT, "/events"), list(date = date_iso))
  events <- if (!is.null(r$body$data)) r$body$data else r$body
  list(events = events, remaining = r$remaining)
}

hist_event_odds <- function(event_id, date_iso) {
  api_get(paste0("/historical/sports/", SPORT, "/events/", event_id, "/odds"),
          list(date = date_iso, regions = REGION, markets = paste(MARKETS, collapse = ","),
               oddsFormat = ODDS_FMT))
}

# ----------------- CHECKPOINT -----------------
ckpt_path <- function(event_id, label) file.path(CKPT_DIR, paste0(event_id, "_", label, ".json"))
already_have <- function(event_id, label) {
  p <- ckpt_path(event_id, label)
  file.exists(p) && file.info(p)$size > 2
}
save_ckpt <- function(event_id, label, body) {
  dir.create(CKPT_DIR, showWarnings = FALSE, recursive = TRUE)
  writeLines(toJSON(body, auto_unbox = TRUE, null = "null"), ckpt_path(event_id, label))
}
read_ckpt <- function(event_id, label) {
  fromJSON(ckpt_path(event_id, label), simplifyVector = FALSE)
}

# ----------------- FLATTEN -----------------
# One snapshot body -> long rows (game, book, market, player, side, line, price),
# then collapsed to one row per (game, player, market) with the median line and
# median over/under price across books.
flatten_snapshot <- function(body, week) {
  ev <- body$data
  if (is.null(ev) || is.null(ev$bookmakers)) return(NULL)
  rows <- list()
  for (bk in ev$bookmakers) {
    for (mkt in bk$markets %||% list()) {
      for (oc in mkt$outcomes %||% list()) {
        rows[[length(rows) + 1]] <- data.frame(
          game_id = ev$id, week = week,
          home_team = ev$home_team %||% NA, away_team = ev$away_team %||% NA,
          commence_time = ev$commence_time %||% NA,
          book = bk$key %||% NA, market = mkt$key %||% NA,
          player = oc$description %||% NA, side = oc$name %||% NA,
          line = as.numeric(oc$point %||% NA), price = as.numeric(oc$price %||% NA),
          stringsAsFactors = FALSE
        )
      }
    }
  }
  if (length(rows) == 0) return(NULL)
  do.call(rbind, rows)
}

consensus <- function(long_df) {
  if (is.null(long_df) || nrow(long_df) == 0) return(long_df)
  key <- interaction(long_df$game_id, long_df$player, long_df$market, drop = TRUE)
  out <- do.call(rbind, lapply(split(long_df, key), function(g) {
    data.frame(
      game_id = g$game_id[1], week = g$week[1],
      home_team = g$home_team[1], away_team = g$away_team[1],
      commence_time = g$commence_time[1],
      market = g$market[1], player = g$player[1],
      book_line = median(g$line, na.rm = TRUE),
      over_price = suppressWarnings(median(g$price[g$side == "Over"], na.rm = TRUE)),
      under_price = suppressWarnings(median(g$price[g$side == "Under"], na.rm = TRUE)),
      n_books = length(unique(g$book)),
      stringsAsFactors = FALSE
    )
  }))
  rownames(out) <- NULL
  out
}

# ----------------- MAIN -----------------
games <- load_schedule(args$schedule, args$season, args$season_type,
                       fbs_only = TRUE, both_fbs = !args$include_one_fbs)
if (!is.na(args$week)) {
  games <- games[games$Week == as.character(args$week), ]
} else if (!is.na(args$week_start)) {
  wk_num <- suppressWarnings(as.integer(games$Week))
  games <- games[!is.na(wk_num) & wk_num >= args$week_start & wk_num <= args$week_end, ]
}
if (!is.na(args$max_games)) games <- head(games, args$max_games)

n_games <- nrow(games)
n_snaps <- length(SNAPSHOTS)
projected <- n_games * n_snaps * length(MARKETS) * HIST_COST_PER

cat(sprintf("Season %s: %d games in scope\n", args$season, n_games))
cat(sprintf("Markets: %d | snapshots/game: %d | region: %s\n", length(MARKETS), n_snaps, REGION))
cat(sprintf("Projected MAX credits (if none cached): %d x %d x %d x %d = %s\n",
            n_games, n_snaps, length(MARKETS), HIST_COST_PER, format(projected, big.mark = ",")))

cached <- if (dir.exists(CKPT_DIR)) {
  sum(sapply(SNAPSHOTS, function(lbl) length(list.files(CKPT_DIR, pattern = paste0("_", lbl, "\\.json$")))))
} else 0
cat(sprintf("Checkpoint dir: %s (%d snapshot file(s) already on disk)\n", CKPT_DIR, cached))

if (projected > CREDIT_CEILING) {
  cat(sprintf("\n*** PROJECTED %s EXCEEDS CEILING %s ***\n", format(projected, big.mark = ","), format(CREDIT_CEILING, big.mark = ",")))
  cat("Reduce scope (--max-games or --week) or raise CREDIT_CEILING deliberately.\n")
  if (!args$dry_run) quit(status = 1)
}

if (args$dry_run) {
  cat("\n[dry-run] No credits spent. Re-run without --dry-run to execute.\n")
  for (i in seq_len(min(3, n_games))) {
    cat(sprintf("  wk%s %s @ %s %s\n", games$Week[i], games$AwayTeam[i], games$HomeTeam[i],
               format(games$commence_dt[i], "%Y-%m-%dT%H:%M:%S%z")))
    for (lbl in SNAPSHOTS) cat(sprintf("      %-8s -> %s\n", lbl, snapshot_iso(games$commence_dt[i], lbl)))
  }
  quit(status = 0)
}

# ---- EXECUTE ----
dir.create(CKPT_DIR, showWarnings = FALSE, recursive = TRUE)
spent_calls <- 0
flat_rows <- list()
halted <- FALSE

for (i in seq_len(n_games)) {
  wk <- games$Week[i]; home <- games$HomeTeam[i]; away <- games$AwayTeam[i]
  disc_iso <- snapshot_iso(games$commence_dt[i], "closing")
  ev_res <- hist_events(disc_iso)
  ev <- match_event(ev_res$events, home, away)
  if (is.null(ev)) {
    cat(sprintf("[%d/%d] wk%s %s@%s: no event match at %s\n", i, n_games, wk, away, home, disc_iso))
    next
  }
  eid <- ev$id

  for (lbl in SNAPSHOTS) {
    if (already_have(eid, lbl)) {
      body <- read_ckpt(eid, lbl)
    } else {
      r <- hist_event_odds(eid, snapshot_iso(games$commence_dt[i], "closing"))
      if (is.null(r$body)) next
      save_ckpt(eid, lbl, r$body)
      spent_calls <- spent_calls + 1
      body <- r$body
      if (!is.na(r$remaining) && r$remaining < CREDIT_FLOOR) {
        cat(sprintf("\n*** remaining credits %d < floor %d. Halting with progress saved. ***\n", r$remaining, CREDIT_FLOOR))
        halted <- TRUE
      }
    }
    rows <- flatten_snapshot(body, wk)
    if (!is.null(rows)) flat_rows[[length(flat_rows) + 1]] <- rows
  }
  if (halted) break
  Sys.sleep(0.25)
  if (i %% 10 == 0) cat(sprintf("[%d/%d] wk%s done\n", i, n_games, wk))
}

cat(sprintf("\nComplete. Pulled %d new (event,snapshot) odds file(s) into %s\n", spent_calls, CKPT_DIR))

if (length(flat_rows) > 0) {
  long_df <- do.call(rbind, flat_rows)
  cons <- consensus(long_df)
  write.csv(cons, args$out, row.names = FALSE)
  cat(sprintf("Wrote %s: %d rows (one per game/player/market)\n", args$out, nrow(cons)))
  cat("Upload that CSV back -- no need to upload hist_raw/ itself.\n")
} else {
  cat("No props flattened (no events matched, or all games were already empty).\n")
}
