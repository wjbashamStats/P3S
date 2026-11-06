import SwiftUI

/// A text field bound to an optional Int. Leave it empty for "not tracked".
struct OptionalIntField: View {
    let title: String
    @Binding var value: Int?

    var body: some View {
        HStack {
            Text(title)
            Spacer()
            TextField("—", text: Binding(
                get: { value.map { String($0) } ?? "" },
                set: { value = Int($0.filter(\.isNumber)) }
            ))
            .keyboardType(.numberPad)
            .multilineTextAlignment(.trailing)
            .frame(maxWidth: 80)
        }
    }
}

struct StatTile: View {
    let title: String
    let value: String
    var caption: String? = nil
    var tint: Color = .green

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.title2.bold())
                .foregroundStyle(tint)
                .lineLimit(1)
                .minimumScaleFactor(0.6)
            if let caption {
                Text(caption)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(.background.secondary, in: RoundedRectangle(cornerRadius: 12))
    }
}

struct TrendBadge: View {
    let trend: Trend

    var body: some View {
        switch trend {
        case .improving:
            Label("Improving", systemImage: "arrow.up.right").foregroundStyle(.green)
        case .declining:
            Label("Slipping", systemImage: "arrow.down.right").foregroundStyle(.red)
        case .flat:
            Label("Steady", systemImage: "arrow.right").foregroundStyle(.secondary)
        case .insufficientData:
            Label("Need more data", systemImage: "ellipsis").foregroundStyle(.secondary)
        }
    }
}

struct RatingView: View {
    @Binding var rating: Int
    var body: some View {
        HStack {
            ForEach(1...5, id: \.self) { i in
                Image(systemName: i <= rating ? "star.fill" : "star")
                    .foregroundStyle(.yellow)
                    .onTapGesture { rating = i }
            }
        }
        .font(.title3)
    }
}
