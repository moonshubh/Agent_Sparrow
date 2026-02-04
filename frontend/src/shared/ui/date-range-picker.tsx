/**
 * DateRangePicker Component
 *
 * Date range selection component using react-day-picker.
 */

"use client";

import * as React from "react";
import { addDays, format } from "date-fns";
import { Calendar as CalendarIcon } from "lucide-react";
import { DateRange } from "react-day-picker";

import { cn } from "@/shared/lib/utils";
import { Button } from "@/shared/ui/button";
import { Calendar } from "@/shared/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/shared/ui/popover";

interface DateRangePickerProps {
  className?: string;
  value?: DateRange;
  onChange?: (range: DateRange | undefined) => void;
  placeholder?: string;
}

/**
 * Deep equality check for DateRange objects
 * Compares actual date values instead of object references
 */
function isDateRangeEqual(
  a: DateRange | undefined,
  b: DateRange | undefined,
): boolean {
  if (a === b) return true;
  if (!a || !b) return false;

  const aFromTime = a.from?.getTime();
  const aToTime = a.to?.getTime();
  const bFromTime = b.from?.getTime();
  const bToTime = b.to?.getTime();

  return aFromTime === bFromTime && aToTime === bToTime;
}

export function DateRangePicker({
  className,
  value,
  onChange,
  placeholder = "Pick a date range",
}: DateRangePickerProps) {
  const [date, setDate] = React.useState<DateRange | undefined>(value);

  // Sync internal state with external value prop when it changes
  React.useEffect(() => {
    if (!isDateRangeEqual(date, value)) {
      setDate(value);
    }
  }, [value, date]);

  // Handle internal date changes and notify parent
  const handleDateChange = React.useCallback(
    (newDate: DateRange | undefined) => {
      setDate(newDate);
      // Only call onChange if the date actually changed
      if (!isDateRangeEqual(newDate, date)) {
        onChange?.(newDate);
      }
    },
    [date, onChange],
  );

  return (
    <div className={cn("grid gap-2", className)}>
      <Popover>
        <PopoverTrigger asChild>
          <Button
            id="date"
            variant={"outline"}
            className={cn(
              "w-[300px] justify-start text-left font-normal",
              !date && "text-muted-foreground",
            )}
          >
            <CalendarIcon className="mr-2 h-4 w-4" />
            {date?.from ? (
              date.to ? (
                <>
                  {format(date.from, "LLL dd, y")} -{" "}
                  {format(date.to, "LLL dd, y")}
                </>
              ) : (
                format(date.from, "LLL dd, y")
              )
            ) : (
              <span>{placeholder}</span>
            )}
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-auto p-0" align="start">
          <Calendar
            initialFocus
            mode="range"
            defaultMonth={date?.from}
            selected={date}
            onSelect={handleDateChange}
            numberOfMonths={2}
          />
        </PopoverContent>
      </Popover>
    </div>
  );
}
