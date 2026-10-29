# Cut down and anonymise one FQResi .Resi file (an R list written by saveRDS).
#
# Usage: Rscript tools/anonymise_resi.R spec.json report.json
#
# spec.json (written by tools/build_corpus.py) holds:
#   strip_reactive_dependents  for old reactivevalues files: empty the Shiny
#                     dependency registry (it captures the server environment)
#   src, out          input and output .Resi paths
#   keep              original df$FileName values to keep (max a few)
#   filename_map      {original FileName: new FileName}
#   column_maps       {column name: {original value: new value}}; applied to df
#                     and to every other data.frame element with that column
#   latlon_offset     [dlat, dlon] magnitudes added to |Lat| and |Lon| (sign
#                     kept), or null
#   compress, version saveRDS() arguments matching the original file
#
# Every element and attribute that is not per-trace or listed above is left
# untouched. The report lists, per element, what was done and a structure
# comparison (class/typeof/attribute names/column classes) old vs new.

suppressPackageStartupMessages({
  library(jsonlite)
  library(data.table)
})

args <- commandArgs(trailingOnly = TRUE)
spec <- fromJSON(args[1], simplifyVector = FALSE)
report_path <- args[2]

PER_TRACE_LISTS <- c("resTraces", "feedTraces", "rPos", "denTraces",
                     "cumDenTraces", "Tppl.Mean.Density", "corrTraces")

obj <- readRDS(spec$src)

# Old Shiny versions saved a reactivevalues object; its data lives in an
# environment inside the R6 implementation object.
is_rv <- inherits(obj, "reactivevalues")
if (is_rv) {
  store <- unclass(obj)$impl$.values
  x <- mget(ls(store, all.names = TRUE), envir = store)
} else {
  x <- obj
}

df <- x$df
n <- nrow(df)

if (isTRUE(spec$probe)) {
  # report the values the anonymiser needs to map: all character/factor
  # columns of every data.frame element (all rows), and the version
  vals <- list()
  for (el in names(x)) if (is.data.frame(x[[el]])) {
    d <- as.data.frame(x[[el]])
    for (cn in names(d)) if (is.character(d[[cn]]) || is.factor(d[[cn]]) || cn %in% c("Lat", "Lon"))
      vals[[el]][[cn]] <- unique(as.character(d[[cn]]))
  }
  writeLines(toJSON(list(values = vals, n = n, FileName = df$FileName,
                         version = if (is.list(x$version)) x$version$version.string else x$version,
                         top_level = names(x), reactivevalues = is_rv),
                    auto_unbox = TRUE, null = "null", na = "null"), report_path)
  quit(status = 0)
}

keep <- unlist(spec$keep)
idx <- sort(match(keep, df$FileName))
if (anyNA(idx)) stop("keep FileName not found in df: ", paste(keep[is.na(match(keep, df$FileName))], collapse = ", "))
k <- length(idx)
kept_fn <- df$FileName[idx]
fn_map <- unlist(spec$filename_map)
col_maps <- lapply(spec$column_maps, unlist)
notes <- character(0)

map_values <- function(v, m, what) {
  if (is.factor(v)) {
    lv <- levels(v)
    hit <- lv %in% names(m)
    lv[hit] <- m[lv[hit]]
    levels(v) <- lv
    return(droplevels(v))
  }
  if (!is.character(v)) return(v)
  hit <- !is.na(v) & v %in% names(m)
  v[hit] <- unname(m[v[hit]])
  v
}

decimals <- function(s) {
  s <- as.character(s)
  ifelse(grepl("\\.", s), nchar(sub("^[^.]*\\.", "", s)), 0L)
}

shift_coord <- function(v, d) {
  # add d to the magnitude, keep the sign and the number of decimals
  if (is.null(v)) return(v)
  if (is.character(v)) {
    num <- suppressWarnings(as.numeric(v))
    ok <- !is.na(num) & is.finite(num) & num != 0
    if (!any(ok)) return(v)
    dec <- decimals(v[ok])
    newv <- sign(num[ok]) * (abs(num[ok]) + d)
    v[ok] <- sprintf(paste0("%.", dec, "f"), newv)
    return(v)
  }
  if (is.numeric(v)) {
    ok <- !is.na(v) & is.finite(v) & v != 0
    if (!any(ok)) return(v)
    dec <- pmin(decimals(format(v[ok], digits = 15, scientific = FALSE, trim = TRUE)), 10L)
    v[ok] <- round(sign(v[ok]) * (abs(v[ok]) + d), dec)
    return(v)
  }
  v
}

subset_rows <- function(d, rows) {
  out <- if (is.data.table(d)) d[rows] else d[rows, , drop = FALSE]
  # keep the original's attribute set: e.g. some files were saved without
  # data.table's .internal.selfref, others carry a "sorted" key (row order is
  # preserved, so it stays valid)
  a0 <- names(attributes(d)); a1 <- names(attributes(out))
  for (a in setdiff(a1, a0)) attr(out, a) <- NULL
  for (a in setdiff(a0, c(a1, "index"))) attr(out, a) <- attr(d, a)
  out
}

anonymise_df <- function(d, is_main) {
  for (cn in names(col_maps)) {
    if (cn %in% names(d)) {
      if (is.data.table(d)) set(d, j = cn, value = map_values(d[[cn]], col_maps[[cn]], cn))
      else d[[cn]] <- map_values(d[[cn]], col_maps[[cn]], cn)
    }
  }
  if ("FileName" %in% names(d)) {
    v <- map_values(d$FileName, fn_map, "FileName")
    if (is.data.table(d)) set(d, j = "FileName", value = v) else d$FileName <- v
  }
  off <- spec$latlon_offset
  if (!is.null(off)) {
    for (pair in list(c("Lat", 1), c("Lon", 2))) {
      cn <- pair[1]
      if (cn %in% names(d)) {
        v <- shift_coord(d[[cn]], as.numeric(off[[as.integer(pair[2])]]))
        if (is.data.table(d)) set(d, j = cn, value = v) else d[[cn]] <- v
      }
    }
  }
  d
}

subset_list <- function(l, name) {
  at <- attributes(l)
  nm <- names(l)
  if (!is.null(nm) && any(nm != "")) {
    sel <- which(nm %in% kept_fn)
    out <- l[sel]
    names(out) <- unname(fn_map[names(out)])
    how <- sprintf("named: kept %d of %d by FileName", length(sel), length(l))
    same <- identical(unname(l[sel]), unname(out))
  } else if (length(l) >= n) {
    out <- l[idx]
    how <- sprintf("positional: kept %d of %d", k, length(l))
    same <- identical(unname(l[idx]), unname(out))
    if (length(l) > n) {
      how <- paste0(how, sprintf(" (original had %d trailing extra element(s), dropped)", length(l) - n))
    }
  } else {
    # rows can't be matched to elements: keep none rather than guess
    out <- list()
    how <- sprintf("unnamed list shorter (%d) than df (%d); rows can't be matched, emptied", length(l), n)
    same <- TRUE
  }
  # restore any non-names attributes (e.g. class)
  for (a in setdiff(names(at), "names")) attr(out, a) <- at[[a]]
  list(value = out, how = how, same = same)
}

actions <- list()
value_mismatch <- character(0)
touched_cols <- c(names(col_maps), "FileName", if (!is.null(spec$latlon_offset)) c("Lat", "Lon"))
check_df <- function(old, newd, el) {
  # every column not deliberately rewritten must be identical
  o <- as.data.frame(old); w <- as.data.frame(newd)
  for (cn in setdiff(names(o), touched_cols))
    if (!identical(o[[cn]], w[[cn]])) value_mismatch <<- c(value_mismatch, paste0(el, "$", cn))
}
new <- x
for (el in names(x)) {
  v <- x[[el]]
  if (is.null(v)) { actions[[el]] <- "NULL, unchanged"; next }
  if (el == "df") {
    v <- subset_rows(v, idx)
    ref <- v
    v <- anonymise_df(v, TRUE)
    check_df(ref, v, el)
    actions[[el]] <- sprintf("kept rows %s of %d; ids/text/serials/coords replaced", paste(idx, collapse = ","), n)
  } else if (is.data.frame(v) && "FileName" %in% names(v)) {
    rows <- which(v$FileName %in% kept_fn)
    actions[[el]] <- sprintf("kept %d of %d rows by FileName", length(rows), nrow(v))
    v <- subset_rows(v, rows)
    ref <- v
    v <- anonymise_df(v, FALSE)
    check_df(ref, v, el)
  } else if (is.data.frame(v)) {
    # per-trace table without FileName (regVar)
    if (nrow(v) == n) {
      v <- subset_rows(v, idx)
      actions[[el]] <- sprintf("positional: kept rows %s of %d", paste(idx, collapse = ","), n)
    } else if (nrow(v) < n && nrow(unique(as.data.frame(v))) <= 1) {
      m <- max(0L, k - (n - nrow(v)))
      v <- subset_rows(v, seq_len(m))
      actions[[el]] <- sprintf("constant table with %d rows for %d traces; kept %d rows (same shortfall)", nrow(x[[el]]), n, m)
    } else {
      actions[[el]] <- sprintf("data.frame %dx%d not per-trace; unchanged", nrow(v), ncol(v))
    }
  } else if (is.list(v) && (el %in% PER_TRACE_LISTS || (!is.null(names(v)) && any(names(v) %in% df$FileName)))) {
    r <- subset_list(v, el)
    v <- r$value
    actions[[el]] <- r$how
    if (!isTRUE(r$same)) value_mismatch <- c(value_mismatch, el)
  } else {
    actions[[el]] <- "unchanged"
  }
  new[el] <- list(v)
}

# ---- structure comparison ----
describe <- function(o) {
  list(class = class(o), typeof = typeof(o),
       attrs = sort(setdiff(names(attributes(o)), c("names", "row.names"))),
       cols = if (is.data.frame(o)) unname(sapply(o, function(z) paste(class(z), collapse = "/"))) else NULL,
       colnames = if (is.data.frame(o)) names(o) else NULL,
       elem_class = if (is.list(o) && !is.data.frame(o) && length(o)) sort(unique(sapply(o, function(z) paste(class(z), collapse = "/")))) else NULL)
}
struct <- list()
mismatch <- character(0)
for (el in names(x)) {
  a <- describe(x[[el]]); b <- describe(new[[el]])
  # a subset may hold fewer kinds of list element than the original
  same <- identical(a[names(a) != "elem_class"], b[names(b) != "elem_class"]) &&
    all(b$elem_class %in% a$elem_class)
  struct[[el]] <- list(same = same, old = a, new = b)
  if (!same) mismatch <- c(mismatch, el)
}
if (!identical(names(x), names(new))) mismatch <- c(mismatch, "<top-level names>")

# ---- write ----
if (is_rv && isTRUE(spec$strip_reactive_dependents)) {
  # The reactive dependency registry holds Shiny contexts whose observers
  # capture the whole server environment (source code, local paths, inputs).
  # It is runtime bookkeeping, not data: empty it.
  deps <- unclass(obj)$impl$.dependents
  actions[[".impl$.dependents"]] <- sprintf("emptied %d reactive dependency entries",
                                            length(ls(deps, all.names = TRUE)))
  rm(list = ls(deps, all.names = TRUE), envir = deps)
}
if (is_rv) {
  for (el in names(new)) assign(el, new[[el]], envir = store)
  out_obj <- obj
} else {
  out_obj <- new
}
compress <- spec$compress
if (identical(compress, "gzip") || identical(compress, TRUE)) compress <- TRUE
saveRDS(out_obj, spec$out, compress = compress, version = as.integer(spec$version))

# re-read and confirm
chk <- readRDS(spec$out)
if (inherits(chk, "reactivevalues")) {
  st <- unclass(chk)$impl$.values
  chk <- mget(ls(st, all.names = TRUE), envir = st)
}
reread_ok <- identical(names(chk), names(new)) && nrow(chk$df) == k &&
  identical(chk$df$FileName, unname(fn_map[kept_fn]))

writeLines(toJSON(list(
  top_level = names(x),
  reactivevalues = is_rv,
  n_before = n, n_after = k, kept_rows = idx,
  actions = actions,
  structure_mismatch = mismatch,
  value_mismatch = value_mismatch,
  summary = list(
    version = if (is.list(new$version)) new$version$version.string else new$version,
    df_columns = names(new$df),
    TraceType = unique(as.character(new$df$TraceType)),
    ResiCode = unique(as.character(new$df$ResiCode)),
    Resource = unique(as.character(c(new$df$Resource, new$df$Species))),
    FileName = as.character(new$df$FileName),
    has_feed = !is.null(new$feedTraces) && length(new$feedTraces) > 0 &&
      any(sapply(new$feedTraces, function(z) { z <- unlist(z); length(z) > 0 && any(!is.na(z) & z != 0) })),
    den_traces = !is.null(new$denTraces) && length(new$denTraces) > 0,
    cum_den_traces = !is.null(new$cumDenTraces) && length(new$cumDenTraces) > 0,
    nonempty = names(new)[sapply(new, function(z) !is.null(z) && length(z) > 0)]
  ),
  structure = struct,
  reread_ok = reread_ok
), auto_unbox = TRUE, null = "null", na = "null", pretty = TRUE), report_path)

if (length(value_mismatch)) {
  message("VALUE MISMATCH in: ", paste(value_mismatch, collapse = ", "))
  quit(status = 4)
}
if (length(mismatch)) {
  message("STRUCTURE MISMATCH in: ", paste(mismatch, collapse = ", "))
  quit(status = 2)
}
if (!reread_ok) { message("re-read check failed"); quit(status = 3) }
